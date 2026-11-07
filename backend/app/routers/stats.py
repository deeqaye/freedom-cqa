"""Quality stats: per-operator weekly/monthly averages (operator view) and an overview across all (admin)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Appeal, Checklist, ChecklistVersion, Conversation, Evaluation
from ..services.cost import PRICES, summarize

router = APIRouter(prefix="/api/stats", tags=["stats"])
UNKNOWN = "Не определён"


def conv_date(c: Conversation) -> datetime:
    try:
        return datetime.fromisoformat(c.started_at)  # calls: ISO 8601
    except (TypeError, ValueError):
        return c.ingested_at  # chats only have MM:SS -> fall back to ingestion date


def bucket(d: datetime, period: str) -> str:
    if period == "month":
        return d.strftime("%Y-%m")
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _rows(db: Session, group_id: str | None, checklist_id: str | None = None):
    """Latest ok evaluation per conversation (optionally only under one checklist)."""
    q = select(Evaluation, Conversation).join(Conversation, Conversation.id == Evaluation.conversation_id) \
        .where(Evaluation.status == "ok").order_by(Evaluation.id)
    if group_id:
        q = q.where(Conversation.dataset_group_id == group_id)
    if checklist_id:
        q = q.join(ChecklistVersion, ChecklistVersion.id == Evaluation.checklist_version_id) \
            .where(ChecklistVersion.checklist_id == checklist_id)
    latest = {}
    for ev, c in db.execute(q).all():
        latest[c.id] = (ev, c)
    return list(latest.values())


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def _summary(rows, period: str) -> dict:
    by_period = defaultdict(list)
    crit = defaultdict(lambda: {"n": 0, "pct_sum": 0.0, "na": 0})
    for ev, c in rows:
        by_period[bucket(conv_date(c), period)].append(ev.final_score)
        for r in (ev.final_breakdown or {}).get("criteria", []):
            k = crit[r["criterion_id"]]
            if r["is_na"]:
                k["na"] += 1
            elif r["weighted"] and r["effective_weight"]:
                k["n"] += 1
                k["pct_sum"] += (r["points"] or 0) / r["effective_weight"] * 100
    return {
        "count": len(rows),
        "avg_score": _avg([ev.final_score for ev, _ in rows]),
        "critical_count": sum(bool(ev.critical_flag) for ev, _ in rows),
        "series": [{"period": p, "avg_score": _avg(v), "count": len(v)} for p, v in sorted(by_period.items())],
        "criteria": {k: {"avg_pct": round(v["pct_sum"] / v["n"], 1) if v["n"] else None, "na": v["na"],
                         "applicable": v["n"]} for k, v in crit.items()},
    }


@router.get("/overview")
def overview(period: Literal["week", "month"] = "week", group_id: str | None = None, checklist_id: str | None = None,
             db: Session = Depends(get_db)):
    rows = _rows(db, group_id, checklist_id)
    ops = defaultdict(list)
    for ev, c in rows:
        ops[c.operator_name or UNKNOWN].append((ev, c))
    by_lang = defaultdict(list)
    for ev, c in rows:
        by_lang[c.language].append(ev.final_score)
    appeals = db.execute(select(Appeal.status)).scalars().all()
    return {
        **_summary(rows, period),
        "by_language": {k: _avg(v) for k, v in sorted(by_lang.items())},
        "operators": sorted([{"operator": k, "count": len(v), "avg_score": _avg([e.final_score for e, _ in v]),
                              "critical_count": sum(bool(e.critical_flag) for e, _ in v)} for k, v in ops.items()],
                            key=lambda x: (x["avg_score"] is None, -(x["avg_score"] or 0))),
        "appeals": {s: appeals.count(s) for s in ("open", "accepted", "rejected")},
    }


@router.get("/operators/{operator}")
def operator_stats(operator: str, period: Literal["week", "month"] = "week", group_id: str | None = None,
                   checklist_id: str | None = None, db: Session = Depends(get_db)):
    rows = [(ev, c) for ev, c in _rows(db, group_id, checklist_id) if (c.operator_name or UNKNOWN) == operator]
    return {"operator": operator, **_summary(rows, period),
            "conversations": [{"id": c.id, "language": c.language, "final_score": ev.final_score,
                               "critical_flag": ev.critical_flag} for ev, c in rows]}


@router.get("/cost")
def cost(group_id: str | None = None, ids: str | None = None, evaluator: str | None = None, latest: bool = True,
         db: Session = Depends(get_db)):
    """Time per evaluation and USD per token. `ids` = one batch (comma-separated evaluation ids); otherwise
    finished evaluations, by default only the latest per conversation. Imported results (no usage) are skipped."""
    q = select(Evaluation, Conversation.channel).join(Conversation, Conversation.id == Evaluation.conversation_id) \
        .where(Evaluation.status.in_(("ok", "error"))).order_by(Evaluation.id)
    if ids:
        q = q.where(Evaluation.id.in_([int(x) for x in ids.split(",") if x]))
    else:
        q = q.where(Evaluation.evaluator != "import")
        if group_id:
            q = q.where(Conversation.dataset_group_id == group_id)
        if evaluator:
            q = q.where(Evaluation.evaluator == evaluator)
    rows = db.execute(q).all()
    if latest and not ids:
        rows = list({ev.conversation_id: (ev, ch) for ev, ch in rows}.values())
    out = summarize(rows)
    if not ids:  # evaluations from different runs: elapsed time between them is not a processing time
        out["time"]["wall_clock_s"] = out["time"]["per_minute"] = None
    return {**out, "prices_usd_per_1m": PRICES}


@router.get("/compare")
def compare(group_id: str | None = None, all_versions: bool = False, db: Session = Depends(get_db)):
    """Same conversations under different checklists: latest ok evaluation per (conversation, checklist version).
    By default one column per checklist (its active version, else the newest one with evaluations); all_versions=true shows every version."""
    q = select(Evaluation, ChecklistVersion, Checklist, Conversation) \
        .join(ChecklistVersion, ChecklistVersion.id == Evaluation.checklist_version_id) \
        .join(Checklist, Checklist.id == ChecklistVersion.checklist_id) \
        .join(Conversation, Conversation.id == Evaluation.conversation_id) \
        .where(Evaluation.status == "ok").order_by(Evaluation.id)
    if group_id:
        q = q.where(Conversation.dataset_group_id == group_id)
    cells, cols = {}, {}
    for ev, ver, cl, c in db.execute(q).all():
        cols[ver.id] = {"version_id": ver.id, "checklist_id": cl.id, "checklist_name": cl.name, "version": ver.version}
        cells[(c.id, ver.id)] = ev
    if not all_versions:  # per checklist: its active version, else the newest version that has evaluations
        active = {cl.id: cl.active_version for cl in db.execute(select(Checklist)).scalars()}
        pick = {}
        for vid, col in cols.items():
            key = (col["version"] == active.get(col["checklist_id"]), col["version"])
            if key > pick.get(col["checklist_id"], ((False, 0), None))[0]:
                pick[col["checklist_id"]] = (key, vid)
        keep = {vid for _, vid in pick.values()}
        cols = {v: c for v, c in cols.items() if v in keep}
        cells = {k: e for k, e in cells.items() if k[1] in keep}
    for vid, col in cols.items():
        evs = [ev for (cid, v), ev in cells.items() if v == vid]
        col.update(count=len(evs), avg_score=_avg([e.final_score for e in evs]),
                   critical_count=sum(bool(e.critical_flag) for e in evs))
    conv_ids = sorted({cid for cid, _ in cells})
    rows = [{"conversation_id": cid,
             "scores": {str(vid): (cells[(cid, vid)].final_score if (cid, vid) in cells else None) for vid in cols},
             "critical": {str(vid): cells[(cid, vid)].critical_flag for vid in cols if (cid, vid) in cells}}
            for cid in conv_ids]
    shared = [r for r in rows if len(r["critical"]) == len(cols)]  # evaluated under every column
    return {"columns": sorted(cols.values(), key=lambda x: (x["checklist_id"] != "chat-quality", x["checklist_id"], x["version"])),
            "rows": rows, "shared_count": len(shared),
            "shared_avg": {str(vid): _avg([r["scores"][str(vid)] for r in shared]) for vid in cols}}

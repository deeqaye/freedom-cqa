"""Builds results.json in the organizers' format (CQA_Student_Guide_Appendix_Results.pdf, schema 1.0)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import TEAM_NAME
from ..models import Conversation, Evaluation


def latest_evaluations(db: Session, group_id: str, checklist_version_id: int | None = None) -> dict[str, Evaluation]:
    """Latest finished (ok/error) evaluation per conversation of the group (optionally for one checklist version)."""
    q = (select(Evaluation).join(Conversation, Conversation.id == Evaluation.conversation_id)
         .where(Conversation.dataset_group_id == group_id, Evaluation.status.in_(("ok", "error"))))
    if checklist_version_id is not None:
        q = q.where(Evaluation.checklist_version_id == checklist_version_id)
    rows = db.execute(q.order_by(Evaluation.created_at, Evaluation.id)).scalars()
    latest: dict[str, Evaluation] = {}
    for ev in rows:
        latest[ev.conversation_id] = ev
    return latest


def build_results(db: Session, group_id: str, checklist_version_id: int | None = None) -> dict:
    convs = db.execute(select(Conversation.id).where(Conversation.dataset_group_id == group_id)
                       .order_by(Conversation.id)).scalars().all()
    latest = latest_evaluations(db, group_id, checklist_version_id)
    results, models, modes = [], [], set()
    for cid in convs:
        ev = latest.get(cid)
        if ev is None:
            results.append({"conversation_id": cid, "status": "error", "criteria": [], "score": None,
                            "error": "Диалог не был оценён."})
            continue
        if ev.status == "error":
            results.append({"conversation_id": cid, "status": "error", "criteria": [], "score": None,
                            "error": ev.error or "Ошибка оценки."})
            continue
        if ev.model_name and ev.model_name not in models:
            models.append(ev.model_name)
        if ev.model_mode:
            modes.add(ev.model_mode)
        results.append({
            "conversation_id": cid,
            "status": "ok",
            "criteria": [{"criterion_id": c["criterion_id"], "value": c["value"], "rationale": c["rationale"],
                          "evidence_turns": c["evidence_turns"]} for c in ev.criteria],
            # system output (before appeals), as the organizers compare model results
            "score": {"final_score": ev.original_score, "critical_flag": bool((ev.breakdown or {}).get("critical_flag"))},
        })
    mode = modes.pop() if len(modes) == 1 else ("hybrid" if modes else "local")
    return {"schema_version": "1.0", "team_name": TEAM_NAME,
            "model": {"mode": mode, "name": ", ".join(models) or "unknown"}, "results": results}


# Criterion codes fixed by the organizers' results format (appendix p.3).
REQUIRED_CRITERIA = {"contact", "discovery", "identification", "consultation", "empathy", "dialogue", "closure", "critical"}


def check_results(doc: dict, expected_ids: list[str] | None = None, expected_count: int | None = None) -> list[str]:
    """Pre-push checks from the appendix. Returns a list of problems (empty == OK)."""
    problems = []
    for r in doc["results"]:
        got = {c["criterion_id"] for c in r["criteria"]}
        if r["status"] == "ok" and got != REQUIRED_CRITERIA:
            problems.append(f"{r['conversation_id']}: criteria {sorted(got ^ REQUIRED_CRITERIA)} differ from the required 8 "
                            "codes - export with the original checklist version (activate v1 or pass the version)")
            break
    ids = [r["conversation_id"] for r in doc["results"]]
    if len(ids) != len(set(ids)):
        problems.append("duplicate conversation_id")
    if expected_ids is not None and set(ids) != set(expected_ids):
        problems.append(f"id mismatch: missing={sorted(set(expected_ids)-set(ids))} extra={sorted(set(ids)-set(expected_ids))}")
    if expected_count is not None and len(ids) != expected_count:
        problems.append(f"expected {expected_count} records, got {len(ids)}")
    for r in doc["results"]:
        if r["status"] == "ok":
            cids = [c["criterion_id"] for c in r["criteria"]]
            if len(cids) != len(set(cids)):
                problems.append(f"{r['conversation_id']}: duplicate criteria")
            if r["score"] is None:
                problems.append(f"{r['conversation_id']}: ok without score")
        elif r["criteria"] or r["score"] is not None or not r.get("error"):
            problems.append(f"{r['conversation_id']}: malformed error record")
    errors = sum(r["status"] == "error" for r in doc["results"])
    if errors:
        problems.append(f"warning: {errors} record(s) with status=error")
    return problems

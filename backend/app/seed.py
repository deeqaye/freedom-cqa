"""Idempotent startup seed: default checklist v1 + local dataset snapshots in data/*.json."""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from .config import DATA_DIR, RESULTS_DIR, SEED_DIR, SEED_RESULTS, SNAPSHOT_DIR
from .models import Checklist, ChecklistVersion, Conversation, Evaluation, now
from .services.ingest import load_file, upsert_payload
from .services.scoring import ValidationError, compute_score, validate_results

log = logging.getLogger("cqa.seed")


def seed_checklist(db: Session) -> None:
    doc = json.loads((SEED_DIR / "checklist_default.json").read_text(encoding="utf-8"))
    if db.get(Checklist, doc["id"]):
        return
    db.add(Checklist(id=doc["id"], name=doc["name"], active_version=1))
    db.add(ChecklistVersion(checklist_id=doc["id"], version=1, criteria=doc["criteria"], note=doc.get("note"),
                            created_by="seed"))
    db.commit()
    log.info("seeded checklist %s v1", doc["id"])


def seed_datasets(db: Session) -> None:
    if db.query(Conversation).first():
        return
    files = {f.name: f for d in (DATA_DIR, SNAPSHOT_DIR) for f in sorted(d.glob("*.json"))}
    for f in files.values():
        try:
            ids = upsert_payload(db, load_file(f))
            log.info("seeded %d conversations from %s", len(ids), f.name)
        except Exception:  # noqa: BLE001
            log.exception("could not seed %s", f)


def seed_results(db: Session) -> None:
    """Fresh deploy: import committed results/*/results.json as evaluations (checklist v1), so the demo
    shows scores without re-running the model. Skipped once any evaluation exists."""
    if db.query(Evaluation).first():
        return
    ver = db.query(ChecklistVersion).filter_by(checklist_id="chat-quality", version=1).one_or_none()
    if not ver:
        return
    n = 0
    for f in sorted(RESULTS_DIR.glob("*/results.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        model = doc.get("model") or {}
        for r in doc.get("results", []):
            if not db.get(Conversation, r["conversation_id"]):
                continue
            ev = Evaluation(conversation_id=r["conversation_id"], checklist_version_id=ver.id, evaluator="import",
                            model_mode=model.get("mode"), model_name=model.get("name"), finished_at=now())
            if r.get("status") == "ok":
                try:
                    validate_results(ver.criteria, r["criteria"])
                except ValidationError as e:
                    log.warning("skip %s from %s: %s", r["conversation_id"], f, e)
                    continue
                by_id = {c["criterion_id"]: c for c in r["criteria"]}
                ev.criteria = [{"criterion_id": c["id"], "value": by_id[c["id"]]["value"],
                                "rationale": by_id[c["id"]].get("rationale", ""),
                                "evidence_turns": by_id[c["id"]].get("evidence_turns") or [],
                                "checked_turns": None,
                                "na_reason": by_id[c["id"]].get("rationale") if by_id[c["id"]]["value"] is None else None}
                               for c in ver.criteria]
                bd = compute_score(ver.criteria, {c["criterion_id"]: c["value"] for c in ev.criteria})
                ev.breakdown = ev.final_breakdown = bd
                ev.original_score = ev.final_score = bd["final_score"]
                ev.critical_flag, ev.status = bd["critical_flag"], "ok"
            else:
                ev.status, ev.error = "error", r.get("error") or "error"
            db.add(ev)
            n += 1
    db.commit()
    if n:
        log.info("imported %d evaluations from results/", n)


def run(db: Session) -> None:
    seed_checklist(db)
    seed_datasets(db)
    if SEED_RESULTS:
        seed_results(db)

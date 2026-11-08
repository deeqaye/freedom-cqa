"""Runs the NLP evaluator on conversations, validates its output and scores it."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from nlp import get_evaluator

from ..config import EVAL_WORKERS
from ..db import SessionLocal
from ..models import ChecklistVersion, Conversation, Evaluation, now
from .cost import normalize_usage
from .ingest import conversation_payload
from .scoring import compute_score, validate_results

log = logging.getLogger("cqa.evaluator")
_pool = ThreadPoolExecutor(max_workers=EVAL_WORKERS, thread_name_prefix="eval")


def checklist_payload(ver: ChecklistVersion) -> dict:
    return {"id": ver.checklist_id, "version": ver.version, "criteria": ver.criteria}


def create_jobs(db: Session, conversation_ids: list[str], ver: ChecklistVersion) -> list[Evaluation]:
    evs = [Evaluation(conversation_id=cid, checklist_version_id=ver.id, status="queued") for cid in conversation_ids]
    db.add_all(evs)
    db.commit()
    return evs


def run_one(evaluation_id: int) -> None:
    db = SessionLocal()
    try:
        ev = db.get(Evaluation, evaluation_id)
        conv = db.get(Conversation, ev.conversation_id)
        ver = db.get(ChecklistVersion, ev.checklist_version_id)
        ev.status = "running"
        db.commit()
        evaluate, name = get_evaluator()
        ev.evaluator = name
        t0 = time.time()
        try:
            out = evaluate(conversation_payload(conv), checklist_payload(ver))
            # Keep only the contract fields, ordered like the checklist.
            by_id = {r["criterion_id"]: r for r in out["criteria"]}
            validate_results(ver.criteria, out["criteria"])
            criteria = [{
                "criterion_id": c["id"],
                "value": by_id[c["id"]]["value"],
                "rationale": by_id[c["id"]].get("rationale", ""),
                "evidence_turns": [int(t) for t in by_id[c["id"]].get("evidence_turns") or []],
                "checked_turns": by_id[c["id"]].get("checked_turns"),
                "na_reason": by_id[c["id"]].get("na_reason"),
                # optional translations of the rationale for the UI language switch (not exported to results.json)
                "rationale_i18n": {lang: by_id[c["id"]][f"rationale_{lang}"] for lang in ("en", "kk")
                                   if isinstance(by_id[c["id"]].get(f"rationale_{lang}"), str) and by_id[c["id"]][f"rationale_{lang}"].strip()} or None,
            } for c in ver.criteria]
            breakdown = compute_score(ver.criteria, {r["criterion_id"]: r["value"] for r in criteria})
            ev.criteria = criteria
            ev.breakdown = ev.final_breakdown = breakdown
            ev.original_score = ev.final_score = breakdown["final_score"]
            ev.critical_flag = breakdown["critical_flag"]
            ev.model_mode = (out.get("model") or {}).get("mode")
            ev.model_name = (out.get("model") or {}).get("name")
            ev.usage = normalize_usage(out.get("usage"), ev.model_name)
            ev.status, ev.error = "ok", None
        except Exception as e:  # noqa: BLE001 — any evaluator failure is recorded, never turned into a zero
            log.exception("evaluation %s failed", evaluation_id)
            ev.status, ev.error = "error", f"{type(e).__name__}: {e}"[:2000]
        ev.duration_s = round(time.time() - t0, 2)
        ev.finished_at = now()
        db.commit()
        u = ev.usage or {}
        log.info("evaluation %s %s %s: %.2fs, in=%s out=%s tokens, $%s", evaluation_id, ev.conversation_id, ev.status,
                 ev.duration_s, u.get("input_tokens"), u.get("output_tokens"), u.get("cost_usd"))
    finally:
        db.close()


def submit(evaluation_ids: list[int]) -> None:
    for eid in evaluation_ids:
        _pool.submit(run_one, eid)


def run_sync(evaluation_ids: list[int]) -> None:
    list(_pool.map(run_one, evaluation_ids))

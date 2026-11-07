from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ChecklistVersion, Conversation, Evaluation
from ..schemas import EvaluateRequest
from ..services import evaluator
from ..services.export import build_results, check_results
from .checklists import get_version
from .conversations import latest_eval

router = APIRouter(prefix="/api", tags=["evaluations"])


def evaluation_out(db: Session, ev: Evaluation) -> dict:
    ver = db.get(ChecklistVersion, ev.checklist_version_id)
    defs = {c["id"]: c for c in ver.criteria}
    rows = []
    bd = {r["criterion_id"]: r for r in ((ev.final_breakdown or {}).get("criteria") or [])}
    orig = {r["criterion_id"]: r for r in ((ev.breakdown or {}).get("criteria") or [])}
    for c in ev.criteria or []:
        d = defs.get(c["criterion_id"], {})
        rows.append({**c, "title": d.get("title"), "section": d.get("section"), "type": d.get("type"),
                     "steps": d.get("steps"), "weight": d.get("weight"), "na_allowed": d.get("na_allowed"),
                     "original_value": orig.get(c["criterion_id"], {}).get("value"),
                     "final_value": bd.get(c["criterion_id"], {}).get("value", c["value"]),
                     "points": bd.get(c["criterion_id"], {}).get("points"),
                     "effective_weight": bd.get(c["criterion_id"], {}).get("effective_weight")})
    return {
        "id": ev.id, "conversation_id": ev.conversation_id, "status": ev.status, "error": ev.error,
        "checklist": {"id": ver.checklist_id, "version": ver.version, "version_id": ver.id},
        "evaluator": ev.evaluator, "model": {"mode": ev.model_mode, "name": ev.model_name}, "usage": ev.usage,
        "original_score": ev.original_score, "final_score": ev.final_score, "critical_flag": ev.critical_flag,
        "sections": (ev.final_breakdown or {}).get("sections"),
        "original_sections": (ev.breakdown or {}).get("sections"),
        "criteria": rows, "duration_s": ev.duration_s, "created_at": ev.created_at, "finished_at": ev.finished_at,
    }


@router.post("/evaluations", status_code=202)
def start_evaluations(body: EvaluateRequest, db: Session = Depends(get_db)):
    """Queue evaluations for given conversations or a whole group, using the active (or given) checklist version."""
    ver = get_version(db, body.checklist_id, body.checklist_version)
    ids = body.conversation_ids or db.execute(
        select(Conversation.id).where(Conversation.dataset_group_id == body.group_id).order_by(Conversation.id)
    ).scalars().all()
    missing = [i for i in ids if not db.get(Conversation, i)]
    if missing or not ids:
        raise HTTPException(404, f"unknown conversations: {missing}" if missing else "no conversations in group")
    evs = evaluator.create_jobs(db, ids, ver)
    eids = [e.id for e in evs]
    if body.wait:
        evaluator.run_sync(eids)
        db.expire_all()
        return {"evaluations": [evaluation_out(db, db.get(Evaluation, i)) for i in eids]}
    evaluator.submit(eids)
    return {"queued": len(eids), "evaluation_ids": eids, "checklist_version": ver.version}


@router.get("/evaluations/progress")
def progress(ids: str, db: Session = Depends(get_db)):
    """Batch progress for comma-separated evaluation ids."""
    id_list = [int(x) for x in ids.split(",") if x]
    rows = db.execute(select(Evaluation.status, func.count()).where(Evaluation.id.in_(id_list))
                      .group_by(Evaluation.status)).all()
    return {s: n for s, n in rows}


@router.get("/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: int, db: Session = Depends(get_db)):
    ev = db.get(Evaluation, evaluation_id)
    if not ev:
        raise HTTPException(404)
    return evaluation_out(db, ev)


@router.get("/conversations/{conversation_id}/evaluation")
def get_conversation_evaluation(conversation_id: str, db: Session = Depends(get_db)):
    ev = latest_eval(db, conversation_id)
    if not ev:
        raise HTTPException(404, "not evaluated yet")
    return evaluation_out(db, ev)


@router.get("/export/{group_id}", tags=["export"])
def export_results(group_id: str, checklist_version_id: int | None = None, db: Session = Depends(get_db)):
    """results.json in the organizers' schema 1.0 for a dataset group."""
    return build_results(db, group_id, checklist_version_id)


@router.get("/export/{group_id}/check", tags=["export"])
def export_check(group_id: str, checklist_version_id: int | None = None, db: Session = Depends(get_db)):
    return {"problems": check_results(build_results(db, group_id, checklist_version_id))}

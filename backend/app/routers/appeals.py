"""Appeals: operator disputes one criterion -> lead/admin accepts (with new value) or rejects -> total recomputed.
The evaluation keeps the original NLP values (`criteria`, `breakdown`, `original_score`); accepted appeals only
affect `final_breakdown` / `final_score`."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Appeal, AppealEvent, ChecklistVersion, Conversation, Evaluation, now
from ..services.scoring import ValidationError, compute_score, validate_value

router = APIRouter(prefix="/api", tags=["appeals"])
REVIEWER_ROLES = {"admin", "lead"}


class AppealIn(BaseModel):
    evaluation_id: int
    criterion_id: str
    comment: str = Field(min_length=3)
    suggested_value: Any = None


class DecisionIn(BaseModel):
    decision: Literal["accept", "reject"]
    new_value: Any = None  # required on accept
    reason: str = Field(min_length=3)
    improvement: str | None = None  # "что можно доработать" — guidance for the operator


def recompute(db: Session, ev: Evaluation) -> None:
    ver = db.get(ChecklistVersion, ev.checklist_version_id)
    values = {c["criterion_id"]: c["value"] for c in ev.criteria}
    for a in db.execute(select(Appeal).where(Appeal.evaluation_id == ev.id, Appeal.status == "accepted")
                        .order_by(Appeal.decided_at)).scalars():
        values[a.criterion_id] = a.new_value
    bd = compute_score(ver.criteria, values)
    ev.final_breakdown, ev.final_score, ev.critical_flag = bd, bd["final_score"], bd["critical_flag"]


def excerpt(conv: Conversation, turns: list[int], ctx: int = 1) -> list[dict]:
    want = set()
    for t in turns or []:
        want.update(range(t - ctx, t + ctx + 1))
    return [t for t in conv.transcript if t["turn"] in want]


def log_event(db: Session, a: Appeal, ev: Evaluation, action: str, role: str, *, old=None, new=None,
              comment: str | None = None, score_before: float | None = None, score_after: float | None = None) -> None:
    ver = db.get(ChecklistVersion, ev.checklist_version_id)
    title = next((c.get("title") for c in ver.criteria if c["id"] == a.criterion_id), None)
    db.add(AppealEvent(appeal_id=a.id, action=action, role=role, conversation_id=ev.conversation_id,
                       criterion_id=a.criterion_id, criterion_title=title, old_value=old, new_value=new,
                       comment=comment, score_before=score_before, score_after=score_after))


def appeal_out(db: Session, a: Appeal, with_context: bool = False) -> dict:
    ev = db.get(Evaluation, a.evaluation_id)
    crit = next((c for c in ev.criteria or [] if c["criterion_id"] == a.criterion_id), {})
    ver = db.get(ChecklistVersion, ev.checklist_version_id)
    d = next((c for c in ver.criteria if c["id"] == a.criterion_id), {})
    out = {"id": a.id, "evaluation_id": a.evaluation_id, "conversation_id": ev.conversation_id,
           "criterion_id": a.criterion_id, "criterion_title": d.get("title"), "criterion_type": d.get("type"),
           "steps": d.get("steps"), "na_allowed": d.get("na_allowed"), "weight": d.get("weight"),
           "original_value": a.original_value, "rationale": crit.get("rationale"),
           "evidence_turns": crit.get("evidence_turns"), "rationale_i18n": crit.get("rationale_i18n"), "comment": a.comment, "author_role": a.author_role,
           "suggested_value": a.suggested_value,
           "status": a.status, "new_value": a.new_value, "reviewer_role": a.reviewer_role,
           "reviewer_comment": a.reviewer_comment, "improvement": a.improvement,
           "score_before": ev.original_score, "score_after": ev.final_score,
           "created_at": a.created_at, "decided_at": a.decided_at}
    if with_context:
        out["excerpt"] = excerpt(db.get(Conversation, ev.conversation_id), crit.get("evidence_turns") or [])
    return out


@router.post("/appeals", status_code=201)
def create_appeal(body: AppealIn, x_role: str = Header(default="operator"), db: Session = Depends(get_db)):
    ev = db.get(Evaluation, body.evaluation_id)
    if not ev or ev.status != "ok":
        raise HTTPException(404, "evaluation not found or not finished")
    crit = next((c for c in ev.criteria if c["criterion_id"] == body.criterion_id), None)
    if crit is None:
        raise HTTPException(404, f"criterion {body.criterion_id} not in this evaluation")
    if db.execute(select(Appeal).where(Appeal.evaluation_id == ev.id, Appeal.criterion_id == body.criterion_id,
                                       Appeal.status == "open")).first():
        raise HTTPException(409, "an open appeal for this criterion already exists")
    a = Appeal(evaluation_id=ev.id, criterion_id=body.criterion_id, comment=body.comment, author_role=x_role,
               original_value=crit["value"], suggested_value=body.suggested_value)
    db.add(a)
    db.flush()
    log_event(db, a, ev, "created", x_role, old=crit["value"], new=body.suggested_value, comment=body.comment,
              score_before=ev.final_score, score_after=ev.final_score)
    db.commit()
    return appeal_out(db, a, with_context=True)


@router.get("/appeals")
def list_appeals(status: str | None = None, conversation_id: str | None = None, evaluation_id: int | None = None,
                 db: Session = Depends(get_db)):
    q = select(Appeal).order_by(Appeal.status != "open", Appeal.created_at.desc())
    if status:
        q = q.where(Appeal.status == status)
    if evaluation_id:
        q = q.where(Appeal.evaluation_id == evaluation_id)
    if conversation_id:
        q = q.join(Evaluation, Evaluation.id == Appeal.evaluation_id).where(Evaluation.conversation_id == conversation_id)
    return [appeal_out(db, a) for a in db.execute(q).scalars()]


@router.get("/appeals/history")
def history(limit: int = 500, conversation_id: str | None = None, db: Session = Depends(get_db)):
    """Stored appeal history (newest first): who filed / accepted / rejected what, value and score changes."""
    q = select(AppealEvent).order_by(AppealEvent.created_at.desc(), AppealEvent.id.desc()).limit(min(limit, 5000))
    if conversation_id:
        q = q.where(AppealEvent.conversation_id == conversation_id)
    rows = db.execute(q).scalars().all()
    total = db.execute(select(func.count()).select_from(AppealEvent)).scalar_one()
    return {"total": total, "events": [
        {"id": e.id, "appeal_id": e.appeal_id, "action": e.action, "role": e.role, "conversation_id": e.conversation_id,
         "criterion_id": e.criterion_id, "criterion_title": e.criterion_title, "old_value": e.old_value,
         "new_value": e.new_value, "comment": e.comment, "score_before": e.score_before,
         "score_after": e.score_after, "created_at": e.created_at} for e in rows]}


@router.delete("/appeals/history")
def clear_history(x_role: str = Header(default="operator"), db: Session = Depends(get_db)):
    """Empty the history log (admin / lead). Appeals themselves and the scores they changed are kept."""
    if x_role not in REVIEWER_ROLES:
        raise HTTPException(403, f"role '{x_role}' cannot clear appeal history")
    n = db.execute(delete(AppealEvent)).rowcount
    db.commit()
    return {"deleted": n}


@router.get("/appeals/{appeal_id}")
def get_appeal(appeal_id: int, db: Session = Depends(get_db)):
    a = db.get(Appeal, appeal_id)
    if not a:
        raise HTTPException(404)
    return appeal_out(db, a, with_context=True)


@router.post("/appeals/{appeal_id}/decision")
def decide(appeal_id: int, body: DecisionIn, x_role: str = Header(default="lead"), db: Session = Depends(get_db)):
    if x_role not in REVIEWER_ROLES:
        raise HTTPException(403, f"role '{x_role}' cannot review appeals")
    a = db.get(Appeal, appeal_id)
    if not a:
        raise HTTPException(404)
    if a.status != "open":
        raise HTTPException(409, f"appeal already {a.status}")
    ev = db.get(Evaluation, a.evaluation_id)
    if body.decision == "accept":
        ver = db.get(ChecklistVersion, ev.checklist_version_id)
        d = next(c for c in ver.criteria if c["id"] == a.criterion_id)
        try:
            validate_value(d, body.new_value)
        except ValidationError as e:
            raise HTTPException(422, str(e)) from e
        a.status, a.new_value = "accepted", body.new_value
    else:
        a.status, a.new_value = "rejected", None
    a.reviewer_role, a.reviewer_comment, a.improvement, a.decided_at = x_role, body.reason, body.improvement, now()
    db.flush()
    before = ev.final_score
    recompute(db, ev)
    log_event(db, a, ev, a.status, x_role, old=a.original_value, new=a.new_value, comment=body.reason,
              score_before=before, score_after=ev.final_score)
    db.commit()
    return appeal_out(db, a, with_context=True)

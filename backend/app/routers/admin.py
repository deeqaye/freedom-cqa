"""Admin maintenance: clear data to start from scratch, or re-load the demo set (DEV + committed results)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import seed
from ..db import get_db
from ..models import Appeal, AppealEvent, Checklist, ChecklistVersion, Conversation, Evaluation

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(x_role: str = Header(default="")) -> str:
    if x_role != "admin":
        raise HTTPException(403, "только администратор")
    return x_role


class ResetIn(BaseModel):
    confirm: str                 # must be "DELETE" — guards against accidental calls
    reset_checklists: bool = False


def counts(db: Session) -> dict:
    return {name: db.execute(select(func.count()).select_from(m)).scalar()
            for name, m in [("conversations", Conversation), ("evaluations", Evaluation), ("appeals", Appeal),
                            ("checklist_versions", ChecklistVersion)]}


@router.get("/counts")
def get_counts(db: Session = Depends(get_db)):
    return counts(db)


@router.post("/reset")
def reset(body: ResetIn, _: str = Depends(require_admin), db: Session = Depends(get_db)):
    """Delete all conversations, evaluations and appeals (optionally checklists -> back to seed v1).
    Stays empty across restarts; use /api/admin/seed-demo to load the demo set again."""
    if body.confirm != "DELETE":
        raise HTTPException(400, 'confirm must be "DELETE"')
    before = counts(db)
    db.execute(delete(AppealEvent))     # history log goes with the data it describes
    db.execute(delete(Appeal))          # FK order: appeals -> evaluations -> conversations
    db.execute(delete(Evaluation))
    db.execute(delete(Conversation))
    if body.reset_checklists:
        db.execute(delete(ChecklistVersion))
        db.execute(delete(Checklist))
    db.commit()
    seed.seed_checklist(db)             # no-op unless checklists were reset
    return {"deleted": before, "now": counts(db)}


@router.post("/seed-demo")
def seed_demo(_: str = Depends(require_admin), db: Session = Depends(get_db)):
    """Load the demo dataset snapshots (DEV) and committed results for conversations without scores."""
    loaded = seed.seed_demo(db)
    return {"loaded": loaded, "now": counts(db)}

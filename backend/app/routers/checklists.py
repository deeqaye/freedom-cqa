from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Checklist, ChecklistVersion
from ..schemas import ChecklistCreate, ChecklistIn

router = APIRouter(prefix="/api/checklists", tags=["checklists"])
EDITOR_ROLES = {"admin", "lead"}


def require_editor(x_role: str = Header(default="admin")) -> str:
    """No auth for the demo: the UI role switcher sends X-Role. Only admin / lead may edit checklists."""
    if x_role not in EDITOR_ROLES:
        raise HTTPException(403, f"role '{x_role}' cannot edit checklists")
    return x_role


def version_out(v: ChecklistVersion, active: int | None = None) -> dict:
    return {"id": v.id, "checklist_id": v.checklist_id, "version": v.version, "active": v.version == active,
            "note": v.note, "created_by": v.created_by, "created_at": v.created_at, "criteria": v.criteria}


def get_version(db: Session, checklist_id: str, version: int | None = None) -> ChecklistVersion:
    cl = db.get(Checklist, checklist_id)
    if not cl:
        raise HTTPException(404, f"checklist {checklist_id} not found")
    v = db.execute(select(ChecklistVersion).where(ChecklistVersion.checklist_id == checklist_id,
                                                  ChecklistVersion.version == (version or cl.active_version))
                   ).scalar_one_or_none()
    if not v:
        raise HTTPException(404, f"version {version} not found")
    return v


@router.get("")
def list_checklists(db: Session = Depends(get_db)):
    out = []
    for cl in db.execute(select(Checklist).order_by(Checklist.created_at)).scalars():
        out.append({"id": cl.id, "name": cl.name, "active_version": cl.active_version,
                    "versions": [v.version for v in cl.versions]})
    return out


@router.get("/{checklist_id}")
def get_checklist(checklist_id: str, version: int | None = None, db: Session = Depends(get_db)):
    cl = db.get(Checklist, checklist_id)
    v = get_version(db, checklist_id, version)
    return {"id": cl.id, "name": cl.name, "active_version": cl.active_version, **{"version": version_out(v, cl.active_version)}}


@router.get("/{checklist_id}/versions")
def list_versions(checklist_id: str, db: Session = Depends(get_db)):
    cl = db.get(Checklist, checklist_id)
    if not cl:
        raise HTTPException(404)
    return [version_out(v, cl.active_version) for v in cl.versions]


@router.post("", status_code=201)
def create_checklist(body: ChecklistCreate, role: str = Depends(require_editor), db: Session = Depends(get_db)):
    if db.get(Checklist, body.id):
        raise HTTPException(409, "checklist already exists")
    db.add(Checklist(id=body.id, name=body.name, active_version=1))
    v = ChecklistVersion(checklist_id=body.id, version=1, note=body.note, created_by=role,
                         criteria=[c.model_dump(exclude_none=True) for c in body.criteria])
    db.add(v)
    db.commit()
    return version_out(v, 1)


@router.put("/{checklist_id}")
def save_new_version(checklist_id: str, body: ChecklistIn, role: str = Depends(require_editor),
                     db: Session = Depends(get_db)):
    """Saving never mutates history: it creates version N+1 (and activates it unless activate=false)."""
    cl = db.get(Checklist, checklist_id)
    if not cl:
        raise HTTPException(404)
    nxt = (db.execute(select(func.max(ChecklistVersion.version)).where(ChecklistVersion.checklist_id == checklist_id)
                      ).scalar() or 0) + 1
    v = ChecklistVersion(checklist_id=checklist_id, version=nxt, note=body.note, created_by=role,
                         criteria=[c.model_dump(exclude_none=True) for c in body.criteria])
    db.add(v)
    if body.name:
        cl.name = body.name
    if body.activate:
        cl.active_version = nxt
    db.commit()
    return version_out(v, cl.active_version)


@router.post("/{checklist_id}/activate/{version}")
def activate(checklist_id: str, version: int, role: str = Depends(require_editor), db: Session = Depends(get_db)):
    v = get_version(db, checklist_id, version)
    cl = db.get(Checklist, checklist_id)
    cl.active_version = v.version
    db.commit()
    return version_out(v, cl.active_version)

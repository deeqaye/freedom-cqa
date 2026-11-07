from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Conversation, Evaluation
from ..services import ingest

router = APIRouter(prefix="/api", tags=["conversations"])


def with_offsets(transcript: list[dict]) -> list[dict]:
    """Adds `t` = seconds from conversation start (chats: MM:SS, calls: ISO 8601) for timeline/audio seeking."""
    from datetime import datetime
    out, t0 = [], None
    for m in transcript:
        ts, t = m.get("timestamp") or "", None
        try:
            if "T" in ts:
                d = datetime.fromisoformat(ts)
                t0 = t0 or d
                t = round((d - t0).total_seconds(), 2)
            else:
                parts = [int(p) for p in ts.split(":")]
                t = float(sum(v * 60 ** i for i, v in enumerate(reversed(parts))))
        except ValueError:
            pass
        out.append({**m, "t": t})
    return out


def latest_eval(db: Session, conversation_id: str) -> Evaluation | None:
    return db.execute(select(Evaluation).where(Evaluation.conversation_id == conversation_id)
                      .order_by(Evaluation.id.desc()).limit(1)).scalar_one_or_none()


class IngestUrlIn(BaseModel):
    url: str
    group_id: str | None = None  # override; default: dataset_group_id from response, else group_id in the link


def _store(db: Session, payload: dict, group: str, save: bool = True) -> dict:
    existing = {c for c in db.execute(select(Conversation.id)).scalars()}
    ids = ingest.upsert_payload(db, payload, group)
    if save:
        ingest.save_snapshot(payload, group)
    new = [i for i in ids if i not in existing]
    return {"group_id": group, "count": len(ids), "new": len(new), "updated": len(ids) - len(new),
            "conversation_ids": ids}


@router.post("/ingest", tags=["ingest"])
def ingest_group(group_id: str, db: Session = Depends(get_db)):
    """Fetch a dataset from the organizers' API by group_id, using the server's ORG_API_URL."""
    try:
        payload = ingest.fetch_group(group_id, save=False)
        group = ingest.safe_group(group_id)
    except ingest.IngestError as e:
        raise HTTPException(502 if "API" in str(e) or "подключиться" in str(e) else 400, str(e)) from e
    return _store(db, payload, group)


@router.post("/ingest/url", tags=["ingest"])
def ingest_url(body: IngestUrlIn, db: Session = Depends(get_db)):
    """Fetch a dataset from a full organizer GET link (including its own group_id).
    Only https links on allowed hosts (INGEST_ALLOWED_HOSTS / ORG_API_URL host) are fetched."""
    try:
        ingest.check_url(body.url)
        payload = ingest.fetch_url(body.url.strip())
        group = ingest.safe_group(body.group_id) if body.group_id else ingest.group_of(payload, body.url)
    except ingest.IngestError as e:
        raise HTTPException(400, str(e)) from e
    return _store(db, payload, group)


@router.post("/conversations/upload", tags=["ingest"])
async def upload(file: UploadFile, group_id: str | None = None, db: Session = Depends(get_db)):
    """Upload a JSON file: the organizers' API response, {records:[...]} or a bare list of records."""
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(413, "Файл больше 50 МБ")
    try:
        payload = ingest.validate_payload(json.loads(raw.decode("utf-8-sig")))
        group = ingest.safe_group(group_id) if group_id else ingest.group_of(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise HTTPException(400, f"Файл не является JSON в UTF-8: {e}") from e
    except ingest.IngestError as e:
        raise HTTPException(400, str(e)) from e
    return _store(db, payload, group)


@router.get("/conversations")
def list_conversations(group_id: str | None = None, language: str | None = None, channel: str | None = None,
                       operator: str | None = None, db: Session = Depends(get_db)):
    q = select(Conversation).order_by(Conversation.dataset_group_id, Conversation.id)
    if group_id:
        q = q.where(Conversation.dataset_group_id == group_id)
    if language:
        q = q.where(Conversation.language == language.upper())
    if channel:
        q = q.where(Conversation.channel == channel)
    if operator:
        q = q.where(Conversation.operator_name == operator)
    convs = db.execute(q).scalars().all()
    # one query for latest evaluation per conversation
    evs = {}
    for ev in db.execute(select(Evaluation).where(Evaluation.conversation_id.in_([c.id for c in convs]))
                         .order_by(Evaluation.id)).scalars():
        evs[ev.conversation_id] = ev
    return [{
        "id": c.id, "group_id": c.dataset_group_id, "channel": c.channel, "language": c.language,
        "operator_name": c.operator_name, "turns": len(c.transcript), "has_audio": bool(c.audio_url),
        "started_at": c.started_at,
        "evaluation": None if c.id not in evs else {
            "id": evs[c.id].id, "status": evs[c.id].status, "final_score": evs[c.id].final_score,
            "original_score": evs[c.id].original_score, "critical_flag": evs[c.id].critical_flag},
    } for c in convs]


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    c = db.get(Conversation, conversation_id)
    if not c:
        raise HTTPException(404)
    ev = latest_eval(db, conversation_id)
    return {"id": c.id, "group_id": c.dataset_group_id, "channel": c.channel, "language": c.language,
            "operator_name": c.operator_name, "audio_url": c.audio_url, "started_at": c.started_at,
            "transcript": with_offsets(c.transcript), "latest_evaluation_id": ev.id if ev else None}

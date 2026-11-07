from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
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


@router.post("/ingest", tags=["ingest"])
def ingest_group(group_id: str, db: Session = Depends(get_db)):
    """Fetch a dataset from the organizers' API by group_id (server-side, no CORS) and store it."""
    try:
        payload = ingest.fetch_group(group_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"organizer API: {e}") from e
    ids = ingest.upsert_payload(db, payload, group_id)
    return {"group_id": group_id, "count": len(ids), "conversation_ids": ids}


@router.post("/conversations/upload", tags=["ingest"])
async def upload(file: UploadFile, group_id: str | None = None, db: Session = Depends(get_db)):
    """Upload a JSON file in the organizers' format ({data:{records:[...]}} or {records:[...]})."""
    import json
    try:
        payload = json.loads(await file.read())
        ids = ingest.upsert_payload(db, payload, group_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"invalid file: {e}") from e
    return {"count": len(ids), "conversation_ids": ids}


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

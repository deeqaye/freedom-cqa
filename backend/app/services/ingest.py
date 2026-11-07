"""Fetch datasets from the organizers' API (server-side, so no CORS) or a local JSON file, and upsert."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from sqlalchemy.orm import Session

from ..config import DATA_DIR, ORG_API_URL
from ..models import Conversation

OPERATOR_NAME = re.compile(r"(?:меня зовут|my name is|менің атым)\s+([A-ZА-ЯЁӘҒҚҢӨҰҮҺІ][\w\-]+)", re.I)


def number_turns(record: dict) -> dict:
    """Copy of the record with a 1-based `turn` on every message (numbering over the full transcript)."""
    rec = copy.deepcopy(record)
    for i, t in enumerate(rec["transcript"], start=1):
        t["turn"] = i
    return rec


def guess_operator(transcript: list[dict]) -> str | None:
    for t in transcript:
        if t["speaker"] == "operator":
            m = OPERATOR_NAME.search(t["text"])
            if m and "скрыто" not in m.group(1).lower():
                return m.group(1).capitalize()
    return None


def with_group_id(base_url: str, group_id: str) -> str:
    """Set group_id on the organizer URL, replacing one already present (the API rejects duplicates).
    Other query params (incl. the URL-encoded `sp`) are kept byte-for-byte."""
    parts = urlsplit(base_url)
    kept = [p for p in parts.query.split("&") if p and not p.split("=", 1)[0] == "group_id"]
    kept.append(urlencode({"group_id": group_id}))
    return urlunsplit(parts._replace(query="&".join(kept)))


def fetch_group(group_id: str, save: bool = True) -> dict:
    if not ORG_API_URL:
        raise RuntimeError("ORG_API_URL is not configured (.env)")
    url = with_group_id(ORG_API_URL, group_id)
    r = httpx.get(url, timeout=60)
    r.raise_for_status()
    payload = r.json()
    if not payload.get("isSuccess"):
        raise RuntimeError(f"Organizer API error: {payload.get('error')}")
    if save:
        (DATA_DIR / f"{group_id}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def load_file(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def upsert_payload(db: Session, payload: dict, group_id: str | None = None) -> list[str]:
    data = payload.get("data", payload)
    group = group_id or data.get("dataset_group_id") or "UPLOAD"
    ids = []
    for rec in data["records"]:
        rec = number_turns(rec)
        conv = db.get(Conversation, rec["conversation_id"]) or Conversation(id=rec["conversation_id"])
        conv.dataset_group_id = group
        conv.channel = rec.get("channel", "agent chat")
        conv.language = rec.get("language", "RU")
        conv.audio_url = rec.get("audio_url")
        conv.transcript = rec["transcript"]
        conv.operator_name = guess_operator(rec["transcript"])
        conv.started_at = rec["transcript"][0]["timestamp"] if rec["transcript"] else None
        db.add(conv)
        ids.append(conv.id)
    db.commit()
    return ids


def conversation_payload(conv: Conversation) -> dict:
    """Shape passed to the NLP evaluator (see nlp/CONTRACT.md)."""
    return {"conversation_id": conv.id, "channel": conv.channel, "language": conv.language,
            "audio_url": conv.audio_url, "transcript": conv.transcript}

"""Audio for calls. The organizers' audio_url returns an HTML player page whose <source> is a short-lived
(1h) signed MP3 link. We resolve it, download once, cache under data/audio/ and serve with Range support
(Starlette FileResponse), so the browser can seek."""
from __future__ import annotations

import html
import re
import threading

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import DATA_DIR
from ..db import get_db
from ..models import Conversation

router = APIRouter(prefix="/api/audio", tags=["audio"])
AUDIO_DIR = DATA_DIR / "audio"
SRC = re.compile(r'<source[^>]+src="([^"]+)"', re.I)
_locks: dict[str, threading.Lock] = {}


def _download(url: str, dest) -> None:
    with httpx.Client(timeout=120, follow_redirects=True) as cl:
        r = cl.get(url)
        r.raise_for_status()
        if "text/html" in r.headers.get("content-type", ""):
            m = SRC.search(r.text)
            if not m:
                raise RuntimeError("no <source> in audio page")
            r = cl.get(html.unescape(m.group(1)))
            r.raise_for_status()
        if not r.headers.get("content-type", "").startswith("audio"):
            raise RuntimeError(f"unexpected content-type {r.headers.get('content-type')}")
        tmp = dest.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.replace(dest)


@router.get("/{conversation_id}")
def get_audio(conversation_id: str, db: Session = Depends(get_db)):
    c = db.get(Conversation, conversation_id)
    if not c or not c.audio_url:
        raise HTTPException(404, "no audio for this conversation")
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    dest = AUDIO_DIR / f"{re.sub(r'[^A-Za-z0-9_-]', '_', conversation_id)}.mp3"
    if not dest.exists():
        with _locks.setdefault(conversation_id, threading.Lock()):
            if not dest.exists():
                try:
                    _download(c.audio_url, dest)
                except Exception as e:  # noqa: BLE001
                    raise HTTPException(502, f"could not fetch audio: {e}") from e
    return FileResponse(dest, media_type="audio/mpeg")

"""Fetch datasets from the organizers' API (server-side, so no CORS) or a local JSON file, and upsert."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx
from sqlalchemy.orm import Session

from ..config import INGEST_ALLOWED_HOSTS, ORG_API_URL, SNAPSHOT_DIR
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


class IngestError(ValueError):
    pass


def allowed_hosts() -> list[str]:
    """Hosts a pasted link may point to. The public server must not fetch arbitrary URLs (SSRF)."""
    hosts = [h.strip().lower() for h in INGEST_ALLOWED_HOSTS.split(",") if h.strip()]
    if ORG_API_URL:
        hosts.append(urlsplit(ORG_API_URL).hostname or "")
    return [h for h in hosts if h]


def check_url(url: str) -> None:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host:
        raise IngestError("Нужна ссылка https://…")
    if not any(host == h or host.endswith("." + h) for h in allowed_hosts()):
        raise IngestError(f"Хост {host} не разрешён. Допустимы: {', '.join(allowed_hosts())}")


def safe_group(group_id: str) -> str:
    g = re.sub(r"[^A-Za-z0-9_.-]", "_", group_id.strip())[:64].strip(".")
    if not g:
        raise IngestError("Пустой group_id")
    return g


def validate_payload(payload) -> dict:
    """Accepts the organizers' response ({isSuccess, data:{records}}) or a bare {records:[...]} / [...]."""
    if isinstance(payload, list):
        payload = {"data": {"records": payload}}
    if not isinstance(payload, dict):
        raise IngestError("Ожидался JSON-объект")
    if payload.get("isSuccess") is False:
        raise IngestError(f"API организаторов вернуло ошибку: {payload.get('error') or 'isSuccess=false'}")
    data = payload.get("data", payload)
    recs = data.get("records") if isinstance(data, dict) else None
    if not isinstance(recs, list) or not recs:
        raise IngestError("В ответе нет data.records")
    for i, r in enumerate(recs):
        if not isinstance(r, dict) or not r.get("conversation_id") or not isinstance(r.get("transcript"), list):
            raise IngestError(f"Запись #{i + 1}: нужны conversation_id и transcript (массив)")
        for j, m in enumerate(r["transcript"]):
            if not isinstance(m, dict) or "speaker" not in m or "text" not in m:
                raise IngestError(f"{r['conversation_id']}, реплика #{j + 1}: нужны speaker и text")
    ids = [r["conversation_id"] for r in recs]
    if len(ids) != len(set(ids)):
        raise IngestError("Повторяющиеся conversation_id в наборе")
    return payload


def fetch_url(url: str) -> dict:
    try:
        r = httpx.get(url, timeout=90, follow_redirects=False)
    except httpx.HTTPError as e:
        raise IngestError(f"Не удалось подключиться: {e}") from e
    if r.status_code != 200:
        raise IngestError(f"API ответило {r.status_code}: {r.text[:200]}")
    try:
        return validate_payload(r.json())
    except json.JSONDecodeError as e:
        raise IngestError("Ответ не является JSON") from e


def group_of(payload: dict, url: str | None = None) -> str:
    data = payload.get("data", payload)
    if data.get("dataset_group_id"):
        return safe_group(str(data["dataset_group_id"]))
    if url:
        q = parse_qs(urlsplit(url).query)
        if q.get("group_id"):
            return safe_group(q["group_id"][0])
    return "UPLOAD"


def save_snapshot(payload: dict, group: str) -> None:
    (SNAPSHOT_DIR / f"{safe_group(group)}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def fetch_group(group_id: str, save: bool = True) -> dict:
    """Fetch by group_id using the configured ORG_API_URL."""
    if not ORG_API_URL:
        raise IngestError("ORG_API_URL не настроен на сервере — вставьте полную ссылку или загрузите файл")
    payload = fetch_url(with_group_id(ORG_API_URL, safe_group(group_id)))
    if save:
        save_snapshot(payload, group_id)
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

"""The evaluator's translated rationales (rationale_en / rationale_kk) reach the UI API, not results.json."""
from fastapi.testclient import TestClient

import app.services.evaluator as svc
from app.main import app
from nlp.stub import evaluate as stub


def with_translations(conversation, checklist):
    out = stub(conversation, checklist)
    for r in out["criteria"]:
        r["rationale_en"], r["rationale_kk"] = f"EN {r['criterion_id']}", f"KK {r['criterion_id']}"
    return out


def test_rationale_translations_are_stored_and_returned(monkeypatch):
    monkeypatch.setattr(svc, "get_evaluator", lambda: (with_translations, "nlp"))
    with TestClient(app) as c:
        ev = c.post("/api/evaluations", json={"conversation_ids": ["p1-kz-002"], "wait": True}).json()["evaluations"][0]
        assert ev["status"] == "ok", ev
        row = next(r for r in c.get(f"/api/evaluations/{ev['id']}").json()["criteria"] if r["criterion_id"] == "contact")
        assert row["rationale_i18n"] == {"en": "EN contact", "kk": "KK contact"} and row["rationale"]
        rec = next(r for r in c.get("/api/export/DEV").json()["results"] if r["conversation_id"] == "p1-kz-002")
        assert set(rec["criteria"][0]) == {"criterion_id", "value", "rationale", "evidence_turns"}  # export unchanged

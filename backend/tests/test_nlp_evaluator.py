"""Offline checks of the teammate's nlp/evaluator.py: the model call is faked, everything else (prompt built from the
checklist, parsing, coercion, retry, translation fallback, usage/cost, service validation) is the real code."""
import json
from pathlib import Path

import pytest

from app.services.scoring import compute_score, validate_results
from nlp import evaluator as E

ROOT = Path(__file__).resolve().parents[2]
CHECKLISTS = {p.stem.removeprefix("checklist_"): json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "seed").glob("checklist_*.json")}
CONV = {"conversation_id": "t-1", "channel": "agent chat", "language": "RU", "audio_url": None, "transcript": [
    {"turn": 1, "speaker": "client", "text": "Где мой тариф?", "timestamp": "00:00"},
    {"turn": 2, "speaker": "bot", "text": "Здравствуйте! Я AIM.", "timestamp": "00:01"},
    {"turn": 3, "speaker": "system", "text": "Эскалация на оператора.", "timestamp": "00:02"},
    {"turn": 4, "speaker": "operator", "text": "Здравствуйте, я Алина. Откройте «Кабинет».", "timestamp": "00:30"},
    {"turn": 5, "speaker": "client", "text": "Нашла, спасибо.", "timestamp": "00:40"},
    {"turn": 6, "speaker": "operator", "text": "Хорошего дня!", "timestamp": "00:45"},
]}


def answer(criteria, bad=None):
    """A model-like JSON answer: the highest allowed value for every criterion (critical=false)."""
    rows = []
    for c in criteria:
        v = max(c["steps"]) if c["type"] == "scale" else (False if c["type"] == "flag" else True)
        rows.append({"criterion_id": c["id"], "reasoning": f"Turn 4 shows {c['id']}.", "value": v, "evidence_turns": [4, 99]})
    if bad:
        rows[0]["value"] = bad
    return json.dumps({"criteria": rows})


class FakeChat:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, model, messages, usage, extra=None):
        self.calls.append(messages)
        usage.inp += 1000
        usage.out += 200
        r = self.replies.pop(0)
        return r(messages) if callable(r) else r


def translation(messages):
    items = json.loads(messages[-1]["content"])["items"]
    return json.dumps({"items": [{"criterion_id": i["criterion_id"], "ru": "Реплика 4 подтверждает.", "kk": "4-реплика."} for i in items]})


@pytest.mark.parametrize("name", sorted(CHECKLISTS))
def test_output_passes_service_validation_for_every_checklist(monkeypatch, name):
    cl = CHECKLISTS[name]
    fake = FakeChat([answer(cl["criteria"]), translation])
    monkeypatch.setattr(E, "_chat", fake)
    out = E.evaluate(CONV, {"id": cl["id"], "version": 1, "criteria": cl["criteria"]})

    validate_results(cl["criteria"], out["criteria"])  # same check the service runs
    assert [r["criterion_id"] for r in out["criteria"]] == [c["id"] for c in cl["criteria"]]
    assert all(r["evidence_turns"] == [4] for r in out["criteria"])  # out-of-range turn 99 dropped
    assert all("Реплика 4" in r["rationale"] for r in out["criteria"])  # Russian rationale from the translation call
    assert out["model"] == {"mode": "external_api", "name": "gpt-6-luna"}
    assert out["usage"]["input_tokens"] == 2000 and out["usage"]["cost_usd"] == pytest.approx((2000 * 0.10 + 400 * 0.50) / 1e6)
    assert compute_score(cl["criteria"], {r["criterion_id"]: r["value"] for r in out["criteria"]})["final_score"] == 100.0
    # the prompt is built from this checklist's own criteria
    prompt = fake.calls[0][0]["content"]
    assert all(f"**{c['id']}**" in prompt for c in cl["criteria"])


def test_invalid_output_is_retried_once_then_raises(monkeypatch):
    crit = CHECKLISTS["default"]["criteria"]
    monkeypatch.setattr(E, "_chat", FakeChat([answer(crit, bad="maybe"), answer(crit), translation]))
    assert E.evaluate(CONV, {"criteria": crit})["criteria"]
    monkeypatch.setattr(E, "_chat", FakeChat([answer(crit, bad="maybe"), answer(crit, bad="maybe")]))
    with pytest.raises(RuntimeError, match="invalid output twice"):
        E.evaluate(CONV, {"criteria": crit})


def test_failed_translation_keeps_english_rationale(monkeypatch):
    crit = CHECKLISTS["default"]["criteria"]
    monkeypatch.setattr(E, "_chat", FakeChat([answer(crit), "not json"]))
    out = E.evaluate(CONV, {"criteria": crit})
    assert out["criteria"][0]["rationale"].startswith("Turn 4 shows")


def test_missing_api_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(E, "_client_obj", None)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        E._client()

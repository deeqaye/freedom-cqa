from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.cost import normalize_usage, price_for, summarize


def test_price_lookup_tolerates_prefixes():
    assert price_for("claude-sonnet-5-5")["input"] == 2.0
    assert price_for("anthropic.claude-sonnet-5-5")["output"] == 10.0
    assert price_for("unknown-model") is None


def test_cost_from_price_table_and_evaluator_cost_wins():
    u = normalize_usage({"input_tokens": 3000, "output_tokens": 600}, "claude-sonnet-5-5")
    assert u["cost_usd"] == 0.012 and u["cost_source"] == "price_table"  # 3000*2/1e6 + 600*10/1e6
    u = normalize_usage({"input_tokens": 3000, "output_tokens": 600, "cost_usd": 0.5}, "claude-sonnet-5-5")
    assert u["cost_usd"] == 0.5 and u["cost_source"] == "evaluator"
    assert "cost_usd" not in normalize_usage({"input_tokens": 1}, "mystery")
    assert normalize_usage(None, "x") is None


def test_summary():
    t0 = datetime(2026, 1, 1)
    mk = lambda st, d, cost, i: SimpleNamespace(status=st, duration_s=d, model_name="m", evaluator="nlp",
                                                 usage={"input_tokens": 1000, "output_tokens": 100, "cost_usd": cost} if cost is not None else None,
                                                 created_at=t0, finished_at=t0 + timedelta(seconds=i))
    s = summarize([(mk("ok", 2.0, 0.01, 10), "chat"), (mk("ok", 4.0, 0.03, 20), "call"), (mk("error", 1.0, None, 30), "chat")])
    assert s["evaluations"] == 3 and s["errors"] == 1
    assert s["time"]["avg_s"] == 2.33 and s["time"]["wall_clock_s"] == 30
    assert s["cost"]["total_usd"] == 0.04 and s["cost"]["avg_per_evaluation_usd"] == 0.02 and s["cost"]["per_1000_usd"] == 20
    assert s["cost"]["unpriced"] == 1 and s["tokens"]["avg_input"] == 1000
    assert s["by_channel"]["call"]["avg_cost_usd"] == 0.03


def test_cost_endpoint():
    from fastapi.testclient import TestClient
    from app.db import SessionLocal
    from app.main import app
    client = TestClient(app).__enter__()
    from app.models import Conversation
    with SessionLocal() as db:
        db.add(Conversation(id="cost-1", dataset_group_id="C", channel="chat", language="ru",
                            transcript=[{"turn": 1, "speaker": "operator", "text": "Здравствуйте"}]))
        db.commit()
    r = client.post("/api/evaluations", json={"conversation_ids": ["cost-1"], "wait": True})
    eid = r.json()["evaluations"][0]["id"]
    c = client.get(f"/api/stats/cost?ids={eid}").json()
    assert c["evaluations"] == 1 and c["time"]["avg_s"] is not None and "claude-sonnet-5-5" in c["prices_usd_per_1m"]
    assert client.get("/api/stats/cost?group_id=C").json()["evaluations"] == 1

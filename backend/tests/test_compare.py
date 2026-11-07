from fastapi.testclient import TestClient

from app.main import app


def test_two_checklists_compare():
    with TestClient(app) as c:
        ids = {x["id"] for x in c.get("/api/checklists").json()}
        assert {"chat-quality", "compliance"} <= ids
        conv = "p1-ru-002"
        for cl in ("chat-quality", "compliance"):
            r = c.post("/api/evaluations", json={"conversation_ids": [conv], "checklist_id": cl, "wait": True})
            assert r.json()["evaluations"][0]["status"] == "ok", r.json()
        evs = c.get(f"/api/conversations/{conv}/evaluations").json()
        assert {e["checklist_id"] for e in evs} >= {"chat-quality", "compliance"}
        one = c.get(f"/api/conversations/{conv}/evaluation?checklist_id=chat-quality").json()
        assert one["checklist"]["id"] == "chat-quality" and one["checklist"]["name"]
        crit = {r["criterion_id"] for r in c.get(f"/api/conversations/{conv}/evaluation?checklist_id=compliance").json()["criteria"]}
        assert {"risk_disclosure", "next_step", "accuracy"} <= crit
        cmp = c.get("/api/stats/compare").json()
        assert len(cmp["columns"]) >= 2 and cmp["shared_count"] >= 1
        row = next(r for r in cmp["rows"] if r["conversation_id"] == conv)
        assert len(row["critical"]) >= 2
        ov = c.get("/api/stats/overview?checklist_id=compliance").json()
        assert "risk_disclosure" in ov["criteria"] and "empathy" not in ov["criteria"]

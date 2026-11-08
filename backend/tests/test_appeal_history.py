from fastapi.testclient import TestClient

from app.main import app


def test_history_is_logged_and_can_be_cleared_without_touching_appeals():
    with TestClient(app) as c:
        ev = c.post("/api/evaluations", json={"conversation_ids": ["p1-kz-001"], "wait": True}).json()["evaluations"][0]
        ap = c.post("/api/appeals", json={"evaluation_id": ev["id"], "criterion_id": "empathy", "comment": "Был вежлив"},
                    headers={"X-Role": "operator"}).json()
        r = c.post(f"/api/appeals/{ap['id']}/decision", json={"decision": "reject", "reason": "Оценка верна"},
                   headers={"X-Role": "lead"})
        assert r.status_code == 200, r.text

        h = c.get("/api/appeals/history").json()
        mine = [e for e in h["events"] if e["appeal_id"] == ap["id"]]
        assert [e["action"] for e in mine] == ["rejected", "created"]  # newest first
        created = mine[1]
        assert created["role"] == "operator" and created["comment"] == "Был вежлив"
        assert created["conversation_id"] == "p1-kz-001" and created["criterion_title"]
        assert mine[0]["role"] == "lead" and mine[0]["comment"] == "Оценка верна"
        assert h["total"] >= 2
        assert c.get("/api/appeals/history?conversation_id=p1-kz-001").json()["events"]

        # only reviewers may clear; clearing keeps appeals and scores
        assert c.delete("/api/appeals/history", headers={"X-Role": "operator"}).status_code == 403
        d = c.delete("/api/appeals/history", headers={"X-Role": "admin"})
        assert d.status_code == 200 and d.json()["deleted"] >= 2
        assert c.get("/api/appeals/history").json() == {"total": 0, "events": []}
        assert c.get(f"/api/appeals/{ap['id']}").json()["status"] == "rejected"

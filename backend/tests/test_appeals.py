from fastapi.testclient import TestClient

from app.main import app


def test_appeal_accept_recomputes_and_keeps_original():
    with TestClient(app) as c:
        ev = c.post("/api/evaluations", json={"conversation_ids": ["p1-ru-005"], "wait": True}).json()["evaluations"][0]
        orig = ev["final_score"]
        dlg = next(x for x in ev["criteria"] if x["criterion_id"] == "dialogue")
        new = 10 if dlg["value"] != 10 else 4

        r = c.post("/api/appeals", json={"evaluation_id": ev["id"], "criterion_id": "dialogue",
                                         "comment": "Ответы были ясными"}, headers={"X-Role": "operator"})
        assert r.status_code == 201, r.text
        ap = r.json()
        assert ap["excerpt"] and ap["original_value"] == dlg["value"]
        # duplicate open appeal
        assert c.post("/api/appeals", json={"evaluation_id": ev["id"], "criterion_id": "dialogue",
                                            "comment": "again"}).status_code == 409
        # operator cannot decide; invalid value rejected
        assert c.post(f"/api/appeals/{ap['id']}/decision", json={"decision": "accept", "new_value": new,
                      "reason": "okay"}, headers={"X-Role": "operator"}).status_code == 403
        assert c.post(f"/api/appeals/{ap['id']}/decision", json={"decision": "accept", "new_value": 5,
                      "reason": "bad step"}, headers={"X-Role": "lead"}).status_code == 422

        r = c.post(f"/api/appeals/{ap['id']}/decision", json={"decision": "accept", "new_value": new,
                   "reason": "Согласен", "improvement": "—"}, headers={"X-Role": "lead"})
        assert r.status_code == 200, r.text
        after = c.get(f"/api/evaluations/{ev['id']}").json()
        assert after["original_score"] == orig and after["final_score"] != orig
        row = next(x for x in after["criteria"] if x["criterion_id"] == "dialogue")
        assert row["original_value"] == dlg["value"] and row["final_value"] == new
        # export still carries the system (original) score
        rec = next(x for x in c.get("/api/export/DEV").json()["results"] if x["conversation_id"] == "p1-ru-005")
        assert rec["score"]["final_score"] == orig

        st = c.get("/api/stats/overview").json()
        assert st["count"] >= 1 and st["appeals"]["accepted"] >= 1
        conv = c.get("/api/conversations/p4-ru-003").json()
        assert conv["transcript"][0]["t"] == 0 and conv["transcript"][-1]["t"] > 300

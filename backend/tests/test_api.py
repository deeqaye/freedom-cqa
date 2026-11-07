import copy

from fastapi.testclient import TestClient

from app.main import app


def test_end_to_end_with_stub():
    with TestClient(app) as c:
        convs = c.get("/api/conversations", params={"group_id": "DEV"}).json()
        assert len(convs) == 65
        conv = c.get("/api/conversations/p1-ru-001").json()
        assert conv["transcript"][0]["turn"] == 1

        r = c.post("/api/evaluations", json={"conversation_ids": ["p1-ru-001", "p4-ru-002"], "wait": True})
        assert r.status_code == 202, r.text
        evs = r.json()["evaluations"]
        assert all(e["status"] == "ok" for e in evs), evs
        assert len(evs[0]["criteria"]) == 8 and evs[0]["final_score"] is not None

        doc = c.get("/api/export/DEV").json()
        assert doc["schema_version"] == "1.0" and len(doc["results"]) == 65
        ok = [x for x in doc["results"] if x["status"] == "ok"]
        assert {x["conversation_id"] for x in ok} == {"p1-ru-001", "p4-ru-002"}
        assert set(ok[0]["criteria"][0]) == {"criterion_id", "value", "rationale", "evidence_turns"}


def test_checklist_versioning_and_criterion_swap():
    with TestClient(app) as c:
        v1 = c.get("/api/checklists/chat-quality").json()["version"]
        criteria = copy.deepcopy(v1["criteria"])
        # organizers' control check: replace one criterion
        criteria[6] = {"id": "followup", "section": "Ведение и завершение диалога", "title": "Срок ответа",
                       "type": "binary", "weight": 5, "na_allowed": True,
                       "na_condition": "Передача вопроса не требовалась.",
                       "description": "Да — оператор назвал срок ответа при передаче вопроса."}
        r = c.put("/api/checklists/chat-quality", json={"criteria": criteria, "note": "swap closure"})
        assert r.status_code == 200, r.text
        assert r.json()["version"] == v1["version"] + 1 and r.json()["active"]

        r = c.post("/api/evaluations", json={"conversation_ids": ["p1-en-001"], "wait": True})
        ev = r.json()["evaluations"][0]
        assert ev["status"] == "ok" and "followup" in [x["criterion_id"] for x in ev["criteria"]]
        assert ev["checklist"]["version"] == v1["version"] + 1

        # operators cannot edit
        assert c.put("/api/checklists/chat-quality", json={"criteria": criteria},
                     headers={"X-Role": "operator"}).status_code == 403
        # invalid: duplicate ids
        assert c.put("/api/checklists/chat-quality", json={"criteria": criteria + [criteria[0]]}).status_code == 422
        c.post(f"/api/checklists/chat-quality/activate/{v1['version']}")

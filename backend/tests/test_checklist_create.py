from fastapi.testclient import TestClient

from app.main import app

TEMPLATE = [{"id": "criterion_1", "section": "Основное", "title": "Новый критерий", "type": "binary", "weight": 100,
             "na_allowed": False, "description": "Да — опишите, когда критерий выполнен.", "na_condition": None,
             "prompt_hint": ""}]


def test_create_from_template_and_copy_then_evaluate():
    with TestClient(app) as c:
        r = c.post("/api/checklists", json={"id": "prodazhi-test", "name": "Продажи (тест)", "criteria": TEMPLATE,
                                            "note": "Создан с нуля"}, headers={"X-Role": "lead"})
        assert r.status_code == 201, r.text
        src = c.get("/api/checklists/chat-quality").json()["version"]["criteria"]
        r = c.post("/api/checklists", json={"id": "copy-test", "name": "Копия", "criteria": src}, headers={"X-Role": "admin"})
        assert r.status_code == 201, r.text
        assert c.post("/api/checklists", json={"id": "copy-test", "name": "x", "criteria": src},
                      headers={"X-Role": "admin"}).status_code == 409
        assert c.post("/api/checklists", json={"id": "op-test", "name": "x", "criteria": TEMPLATE},
                      headers={"X-Role": "operator"}).status_code == 403
        ids = [x["id"] for x in c.get("/api/checklists").json()]
        assert {"prodazhi-test", "copy-test"} <= set(ids)
        ev = c.post("/api/evaluations", json={"conversation_ids": ["p1-ru-001"], "checklist_id": "prodazhi-test",
                                              "wait": True}).json()["evaluations"][0]
        assert ev["status"] == "ok", ev
        assert ev["checklist"]["id"] == "prodazhi-test" and [x["criterion_id"] for x in ev["criteria"]] == ["criterion_1"]

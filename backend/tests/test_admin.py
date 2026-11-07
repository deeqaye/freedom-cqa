from fastapi.testclient import TestClient

from app import seed
from app.db import SessionLocal
from app.main import app


def test_reset_stays_empty_after_restart_and_demo_reload():
    with TestClient(app) as c:
        c.post("/api/evaluations", json={"conversation_ids": ["p1-ru-002"], "wait": True})
        h = {"X-Role": "admin"}
        assert c.post("/api/admin/reset", json={"confirm": "DELETE"}, headers={"X-Role": "lead"}).status_code == 403
        assert c.post("/api/admin/reset", json={"confirm": "yes"}, headers=h).status_code == 400
        r = c.post("/api/admin/reset", json={"confirm": "DELETE"}, headers=h)
        assert r.status_code == 200 and r.json()["now"]["conversations"] == 0 and r.json()["now"]["evaluations"] == 0
        assert r.json()["now"]["checklist_versions"] >= 1  # checklists kept by default
    # simulated restart: startup seeding must NOT refill a deliberately cleared database
    with SessionLocal() as db:
        seed.run(db)
    with TestClient(app) as c:
        assert c.get("/api/conversations").json() == []
        r = c.post("/api/admin/seed-demo", headers={"X-Role": "admin"})
        assert r.status_code == 200 and r.json()["now"]["conversations"] == 65
        # reset checklists back to the seed v1
        c.put("/api/checklists/chat-quality", json={"criteria": c.get("/api/checklists/chat-quality").json()["version"]["criteria"]})
        r = c.post("/api/admin/reset", json={"confirm": "DELETE", "reset_checklists": True}, headers={"X-Role": "admin"})
        assert r.json()["now"]["checklist_versions"] == 2  # seed v1 of each seed checklist
        c.post("/api/admin/seed-demo", headers={"X-Role": "admin"})  # leave data for other tests

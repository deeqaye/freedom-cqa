import json

from app import seed
from app.config import RESULTS_DIR
from app.db import Base, SessionLocal, engine
from app.models import Evaluation
from app.services.export import build_results


def test_import_committed_results_roundtrip(tmp_path, monkeypatch):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed.seed_checklist(db)
        seed.seed_datasets(db)
        db.query(Evaluation).delete()  # other tests may have created evaluations
        db.commit()
        src = json.loads((RESULTS_DIR / "dev" / "results.json").read_text())
        seed.seed_results(db)
        doc = build_results(db, "DEV")
    # importing then exporting must reproduce the committed file's results
    assert {r["conversation_id"]: r["score"] for r in doc["results"]} == {r["conversation_id"]: r["score"] for r in src["results"]}

"""Write results/<dev|prod>/results.json in the organizers' format and validate it.

  python scripts/export_results.py DEV            -> results/dev/results.json  (expects 65 records)
  python scripts/export_results.py <PROD_GROUP> --prod  -> results/prod/results.json (expects 10)
  add --evaluate to (re)run evaluation of the whole group first (active checklist version)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app import seed  # noqa: E402
from app.config import RESULTS_DIR  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Checklist, ChecklistVersion, Conversation  # noqa: E402
from app.services import evaluator  # noqa: E402
from app.services.export import build_results, check_results  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("group_id")
    ap.add_argument("--prod", action="store_true", help="write to results/prod and expect 10 records")
    ap.add_argument("--evaluate", action="store_true", help="evaluate the whole group first")
    ap.add_argument("--checklist", default="chat-quality")
    ap.add_argument("--version", type=int, help="checklist version to evaluate/export (default: active)")
    args = ap.parse_args()

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed.run(db)
        ids = db.execute(select(Conversation.id).where(Conversation.dataset_group_id == args.group_id)).scalars().all()
        if not ids:
            print(f"No conversations for group {args.group_id}. Ingest first: POST /api/ingest?group_id=...")
            return 2
        cl = db.get(Checklist, args.checklist)
        ver = db.execute(select(ChecklistVersion).where(ChecklistVersion.checklist_id == cl.id,
                                                        ChecklistVersion.version == (args.version or cl.active_version))).scalar_one()
        version_id = ver.id
        if args.evaluate:
            evs = evaluator.create_jobs(db, ids, ver)
            print(f"evaluating {len(evs)} conversations with {cl.id} v{ver.version} ...")
            evaluator.run_sync([e.id for e in evs])
        db.expire_all()
        doc = build_results(db, args.group_id, version_id)

    expected = 10 if args.prod else None
    problems = check_results(doc, expected_ids=ids, expected_count=expected)
    out = RESULTS_DIR / ("prod" if args.prod else "dev") / "results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(r["status"] == "ok" for r in doc["results"])
    print(f"wrote {out.relative_to(ROOT)}: {len(doc['results'])} records ({ok} ok), model={doc['model']}")
    for p in problems:
        print("  !", p)
    hard = [p for p in problems if not p.startswith("warning")]
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())

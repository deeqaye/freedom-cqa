"""Self-check for the NLP evaluator: python -m nlp.check [conversation_id ...]"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.scoring import ValidationError, compute_score, validate_results  # noqa: E402
from app.services.ingest import number_turns  # noqa: E402
from nlp import get_evaluator  # noqa: E402

DEFAULT_IDS = ["p1-ru-001", "p1-kz-001", "p1-en-001", "p1-ru-010", "p4-ru-002"]


def main(ids: list[str]) -> int:
    data_file = ROOT / "data" / "DEV.json"
    if not data_file.exists():
        print(f"Missing {data_file}. Fetch it: curl -X POST 'localhost:8000/api/ingest?group_id=DEV'")
        return 2
    records = {r["conversation_id"]: r for r in json.loads(data_file.read_text())["data"]["records"]}
    checklist = json.loads((ROOT / "seed" / "checklist_default.json").read_text())
    checklist["version"] = 1
    evaluate, name = get_evaluator()
    print(f"evaluator: {name}")
    failed = 0
    for cid in ids or DEFAULT_IDS:
        conv = number_turns(records[cid])
        t0 = time.time()
        try:
            out = evaluate(conv, checklist)
            validate_results(checklist["criteria"], out["criteria"])
            assert out.get("model", {}).get("name"), "model.name missing"
            assert out["model"].get("mode") in ("local", "external_api", "hybrid"), "model.mode invalid"
            n = len(conv["transcript"])
            for r in out["criteria"]:
                assert r.get("rationale"), f"{r['criterion_id']}: empty rationale"
                assert r.get("evidence_turns"), f"{r['criterion_id']}: empty evidence_turns"
                bad = [t for t in r["evidence_turns"] if not (isinstance(t, int) and 1 <= t <= n)]
                assert not bad, f"{r['criterion_id']}: evidence_turns out of range 1..{n}: {bad}"
            score = compute_score(checklist["criteria"], {r["criterion_id"]: r["value"] for r in out["criteria"]})
            vals = " ".join(f"{r['criterion_id']}={r['value']}" for r in out["criteria"])
            print(f"OK   {cid:10} {time.time()-t0:5.1f}s score={score['final_score']} critical={score['critical_flag']} | {vals}")
        except (ValidationError, AssertionError, Exception) as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {cid:10} {type(e).__name__}: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

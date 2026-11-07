"""Self-check for the NLP evaluator.

  python -m nlp.check                          5 DEV conversations, default checklist
  python -m nlp.check p1-ru-001 p4-ru-002      chosen conversations
  python -m nlp.check --checklist compliance   the second (mock) checklist: different ids, weights, scale
  python -m nlp.check --all                    all 65 DEV conversations
  python -m nlp.check --dump nlp/examples      also write the exact input and your output per conversation
"""
from __future__ import annotations

import argparse
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


def load_checklist(name: str) -> dict:
    f = Path(name) if name.endswith(".json") else ROOT / "seed" / f"checklist_{name}.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    return {"id": doc["id"], "version": 1, "criteria": doc["criteria"]}  # exactly what the service passes


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m nlp.check")
    ap.add_argument("ids", nargs="*", help="conversation ids (default: 5 mixed DEV conversations)")
    ap.add_argument("--checklist", default="default", help="default | compliance | path/to/checklist.json")
    ap.add_argument("--all", action="store_true", help="all DEV conversations")
    ap.add_argument("--dump", metavar="DIR", help="write <id>.input.json and <id>.output.json")
    args = ap.parse_args(argv)
    data_file = ROOT / "data" / "DEV.json"
    if not data_file.exists():
        print(f"Missing {data_file}. Fetch it: curl -X POST 'localhost:8000/api/ingest?group_id=DEV'")
        return 2
    records = {r["conversation_id"]: r for r in json.loads(data_file.read_text())["data"]["records"]}
    checklist = load_checklist(args.checklist)
    ids = sorted(records) if args.all else (args.ids or DEFAULT_IDS)
    dump = Path(args.dump) if args.dump else None
    if dump:
        dump.mkdir(parents=True, exist_ok=True)
    evaluate, name = get_evaluator()
    print(f"evaluator: {name} · checklist: {checklist['id']} ({len(checklist['criteria'])} criteria)")
    failed, times = 0, []
    for cid in ids:
        r = records[cid]
        conv = number_turns({k: r.get(k) for k in ("conversation_id", "channel", "language", "audio_url", "transcript")})
        t0 = time.time()
        try:
            if dump:
                (dump / f"{cid}.input.json").write_text(json.dumps({"conversation": conv, "checklist": checklist},
                                                                   ensure_ascii=False, indent=2), encoding="utf-8")
            out = evaluate(conv, checklist)
            if dump:
                (dump / f"{cid}.output.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
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
            times.append(time.time() - t0)
            print(f"OK   {cid:10} {times[-1]:5.1f}s score={score['final_score']} critical={score['critical_flag']} | {vals}")
        except (ValidationError, AssertionError, Exception) as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {cid:10} {type(e).__name__}: {e}")
    if times:
        print(f"{len(times)} ok, {failed} failed · avg {sum(times) / len(times):.1f}s per conversation")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

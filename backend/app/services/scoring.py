"""Deterministic scoring. The NLP part returns raw values only; all math lives here.

Rules (CQA_Chat_Quality_Checklist.pdf, p.2):
  - binary: true -> full weight, false -> 0
  - scale: weight * value / max(steps)  (top step == full weight)
  - flag:  no points; any flag criterion == true sets critical_flag (score is NOT zeroed)
  - null (N/A) on a criterion that allows it -> excluded, weight redistributed proportionally
  - final = earned / sum(applicable weights) * 100, rounded to 2 decimals (half-up)
  - no applicable weighted criteria -> final_score is None
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any


class ValidationError(ValueError):
    pass


def round2(x: float) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def validate_value(criterion: dict, value: Any) -> None:
    cid, ctype = criterion["id"], criterion["type"]
    if value is None:
        if not criterion.get("na_allowed"):
            raise ValidationError(f"{cid}: N/A (null) is not allowed")
        return
    if ctype in ("binary", "flag"):
        if not isinstance(value, bool):
            raise ValidationError(f"{cid}: expected true/false, got {value!r}")
    elif ctype == "scale":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value not in criterion["steps"]:
            raise ValidationError(f"{cid}: expected one of {criterion['steps']}, got {value!r}")
    else:
        raise ValidationError(f"{cid}: unknown criterion type {ctype!r}")


def validate_results(criteria: list[dict], results: list[dict]) -> None:
    """Every checklist criterion exactly once, no unknown ids, allowed values only."""
    expected = [c["id"] for c in criteria]
    got = [r.get("criterion_id") for r in results]
    missing = set(expected) - set(got)
    extra = set(got) - set(expected)
    dups = {x for x in got if got.count(x) > 1}
    errs = []
    if missing:
        errs.append(f"missing criteria: {sorted(missing)}")
    if extra:
        errs.append(f"unknown criteria: {sorted(extra)}")
    if dups:
        errs.append(f"duplicate criteria: {sorted(dups)}")
    by_id = {c["id"]: c for c in criteria}
    for r in results:
        c = by_id.get(r.get("criterion_id"))
        if c is None:
            continue
        try:
            validate_value(c, r.get("value"))
        except ValidationError as e:
            errs.append(str(e))
    if errs:
        raise ValidationError("; ".join(errs))


def raw_points(criterion: dict, value: Any) -> float:
    w = float(criterion["weight"])
    if criterion["type"] == "binary":
        return w if value else 0.0
    if criterion["type"] == "scale":
        return w * float(value) / float(max(criterion["steps"]))
    return 0.0


def compute_score(criteria: list[dict], values: dict[str, Any]) -> dict:
    """values: {criterion_id: value}. Returns final score + per-criterion and per-section breakdown."""
    applicable_weight = 0.0
    earned = 0.0
    critical_flag = False
    rows = []
    for c in criteria:
        v = values.get(c["id"])
        is_na = v is None and c.get("na_allowed", False)
        weighted = c["type"] != "flag" and float(c.get("weight", 0)) > 0
        pts = 0.0
        if c["type"] == "flag" and v is True:
            critical_flag = True
        if weighted and not is_na:
            pts = raw_points(c, v)
            applicable_weight += float(c["weight"])
            earned += pts
        rows.append({"criterion_id": c["id"], "section": c.get("section"), "value": v, "is_na": is_na,
                     "weighted": weighted, "weight": c.get("weight", 0), "raw_points": pts})

    final = round2(earned / applicable_weight * 100) if applicable_weight > 0 else None

    sections: dict[str, dict] = {}
    for r in rows:
        if r["weighted"] and not r["is_na"]:
            eff = float(r["weight"]) / applicable_weight * 100
            r["effective_weight"] = round2(eff)
            r["points"] = round2(r["raw_points"] / applicable_weight * 100)
            s = sections.setdefault(r["section"] or "", {"earned": 0.0, "max": 0.0})
            s["earned"] += r["raw_points"] / applicable_weight * 100
            s["max"] += eff
        else:
            r["effective_weight"] = 0.0
            r["points"] = None if r["is_na"] or not r["weighted"] else 0.0
        del r["raw_points"]
    for s in sections.values():
        s["earned"], s["max"] = round2(s["earned"]), round2(s["max"])

    return {"final_score": final, "critical_flag": critical_flag, "criteria": rows, "sections": sections}

import json
from pathlib import Path

import pytest

from app.services.scoring import ValidationError, compute_score, validate_results

CRITERIA = json.loads((Path(__file__).resolve().parents[2] / "seed" / "checklist_default.json").read_text())["criteria"]


def test_appendix_example_85_38():
    # Example from CQA_Student_Guide_Appendix_Results.pdf p.2
    vals = {"contact": True, "discovery": None, "identification": None, "consultation": 15,
            "empathy": True, "dialogue": 7, "closure": True, "critical": False}
    r = compute_score(CRITERIA, vals)
    assert r["final_score"] == 85.38
    assert r["critical_flag"] is False


def test_all_perfect_is_100():
    vals = {"contact": True, "discovery": True, "identification": True, "consultation": 20,
            "empathy": True, "dialogue": 10, "closure": True, "critical": False}
    assert compute_score(CRITERIA, vals)["final_score"] == 100.0


def test_all_zero():
    vals = {"contact": False, "discovery": False, "identification": False, "consultation": 0,
            "empathy": False, "dialogue": 0, "closure": False, "critical": False}
    assert compute_score(CRITERIA, vals)["final_score"] == 0.0


def test_critical_does_not_zero_score():
    vals = {"contact": True, "discovery": True, "identification": True, "consultation": 20,
            "empathy": True, "dialogue": 10, "closure": True, "critical": True}
    r = compute_score(CRITERIA, vals)
    assert r["final_score"] == 100.0 and r["critical_flag"] is True


def test_na_redistribution_effective_weights_sum_100():
    vals = {"contact": True, "discovery": None, "identification": None, "consultation": None,
            "empathy": False, "dialogue": 4, "closure": None, "critical": False}
    r = compute_score(CRITERIA, vals)
    # applicable: contact 10, empathy 15, dialogue 15 -> 40; earned 10 + 0 + 6 = 16 -> 40.0
    assert r["final_score"] == 40.0
    assert round(sum(c["effective_weight"] for c in r["criteria"]), 1) == 100.0
    assert r["sections"]["Начало и понимание запроса"] == {"earned": 25.0, "max": 25.0}


def test_rounding_half_up():
    # applicable: contact 10 + dialogue 15 = 25... choose values producing x.xx5
    crit = [{"id": "a", "type": "binary", "weight": 3, "na_allowed": False},
            {"id": "b", "type": "binary", "weight": 5, "na_allowed": False}]
    # 3/8*100 = 37.5 exact; use weights 1 and 7 -> 12.5; check a .xx5 case: 1/16*100=6.25
    crit2 = [{"id": "a", "type": "binary", "weight": 1, "na_allowed": False},
             {"id": "b", "type": "binary", "weight": 15, "na_allowed": False}]
    assert compute_score(crit, {"a": True, "b": False})["final_score"] == 37.5
    assert compute_score(crit2, {"a": True, "b": False})["final_score"] == 6.25
    crit3 = [{"id": "a", "type": "binary", "weight": 1, "na_allowed": False},
             {"id": "b", "type": "binary", "weight": 2, "na_allowed": False}]
    assert compute_score(crit3, {"a": True, "b": False})["final_score"] == 33.33


def test_no_applicable_criteria_gives_none():
    crit = [{"id": "a", "type": "binary", "weight": 10, "na_allowed": True, "na_condition": "x"},
            {"id": "f", "type": "flag", "weight": 0, "na_allowed": False}]
    assert compute_score(crit, {"a": None, "f": False})["final_score"] is None


def _results(**over):
    base = {"contact": True, "discovery": True, "identification": None, "consultation": 15,
            "empathy": True, "dialogue": 7, "closure": True, "critical": False}
    base.update(over)
    return [{"criterion_id": k, "value": v} for k, v in base.items()]


def test_validate_ok():
    validate_results(CRITERIA, _results())


@pytest.mark.parametrize("bad", [
    {"dialogue": 6},          # not a step
    {"contact": None},        # N/A not allowed
    {"empathy": "true"},      # wrong type
    {"consultation": True},   # bool is not a scale value
    {"critical": None},
])
def test_validate_rejects(bad):
    with pytest.raises(ValidationError):
        validate_results(CRITERIA, _results(**bad))


def test_validate_missing_and_duplicate():
    res = _results()
    with pytest.raises(ValidationError, match="missing"):
        validate_results(CRITERIA, res[:-1])
    with pytest.raises(ValidationError, match="duplicate"):
        validate_results(CRITERIA, res + [res[0]])

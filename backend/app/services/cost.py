"""Processing cost: time per evaluation and USD per token.

The evaluator reports `usage` (tokens, optionally `cost_usd`). If it gives no cost, the service prices the
tokens with PRICES (USD per 1M tokens). Override or extend PRICES with env MODEL_PRICES, e.g.
  MODEL_PRICES='{"gpt-5-mini": {"input": 0.25, "output": 2.0}}'
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from statistics import median

# USD per 1M tokens (Anthropic first-party list prices). cache_write = 5-min cache write (1.25x input).
PRICES: dict[str, dict[str, float]] = {
    "claude-fable-5-1": {"input": 10.0, "output": 50.0, "cache_read": 0.25, "cache_write": 12.5},
    "claude-fable-5": {"input": 10.0, "output": 50.0, "cache_read": 1.0, "cache_write": 12.5},
    "claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_read": 0.20, "cache_write": 5.0},
    "claude-opus-5": {"input": 5.0, "output": 25.0, "cache_read": 0.50, "cache_write": 6.25},
    "claude-opus-4-8": {"input": 5.0, "output": 25.0, "cache_read": 0.50, "cache_write": 6.25},
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.20, "cache_write": 2.5},
    "claude-sonnet-5": {"input": 2.0, "output": 10.0, "cache_read": 0.20, "cache_write": 2.5},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0, "cache_read": 0.10, "cache_write": 1.25},
    "gpt-6-luna": {"input": 0.10, "output": 0.50},  # teammate's evaluator (it also reports cost_usd itself)
    "keyword-stub": {"input": 0.0, "output": 0.0},
}
try:
    PRICES.update(json.loads(os.getenv("MODEL_PRICES", "") or "{}"))
except json.JSONDecodeError:
    pass

TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def price_for(model: str | None) -> dict | None:
    """Price row for a model name; tolerates provider prefixes and suffixes ("anthropic.claude-...", "...-v1")."""
    if not model:
        return None
    m = model.lower().split("/")[-1].removeprefix("anthropic.")
    if m in PRICES:
        return PRICES[m]
    best = max((k for k in PRICES if m.startswith(k)), key=len, default=None)
    return PRICES.get(best) if best else None


def token_cost(usage: dict, price: dict) -> float:
    return (usage.get("input_tokens", 0) * price.get("input", 0)
            + usage.get("output_tokens", 0) * price.get("output", 0)
            + usage.get("cache_read_input_tokens", 0) * price.get("cache_read", price.get("input", 0))
            + usage.get("cache_creation_input_tokens", 0) * price.get("cache_write", price.get("input", 0))) / 1e6


def normalize_usage(usage: dict | None, model_name: str | None) -> dict | None:
    """Ints for token counts; fill cost_usd from the price table when the evaluator gave none.
    A model name may be "a + b" (hybrid); then only an evaluator-given cost is trusted."""
    if not isinstance(usage, dict):
        return None
    u = {k: v for k, v in usage.items()}
    for k in TOKEN_KEYS:
        if k in u:
            u[k] = int(u[k] or 0)
    if u.get("cost_usd") is not None:
        u["cost_usd"] = float(u["cost_usd"])
        u.setdefault("cost_source", "evaluator")
    else:
        price = price_for(model_name)
        if price and any(k in u for k in TOKEN_KEYS):
            u["cost_usd"] = round(token_cost(u, price), 6)
            u["cost_source"] = "price_table"
    return u


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))], 2)


def _r(x, n=2):
    return None if x is None else round(x, n)


def summarize(rows) -> dict:
    """rows: iterable of (Evaluation, channel). Time over all finished evaluations; cost over those with usage."""
    rows = [(ev, ch) for ev, ch in rows if ev.status in ("ok", "error")]
    durs = [ev.duration_s for ev, _ in rows if ev.duration_s is not None]
    tok = defaultdict(int)
    costs, measured_tok = [], 0
    by_model = defaultdict(lambda: {"count": 0, "cost_usd": 0.0, "dur": [], "priced": 0})
    by_channel = defaultdict(lambda: {"count": 0, "cost": [], "dur": [], "tokens": []})
    for ev, ch in rows:
        u = ev.usage or {}
        has_tok = any(k in u for k in TOKEN_KEYS)
        if has_tok:
            measured_tok += 1
            for k in TOKEN_KEYS:
                tok[k] += u.get(k, 0) or 0
        m = by_model[ev.model_name or ev.evaluator or "?"]
        m["count"] += 1
        c = by_channel[ch or "?"]
        c["count"] += 1
        if ev.duration_s is not None:
            m["dur"].append(ev.duration_s)
            c["dur"].append(ev.duration_s)
        if has_tok:
            c["tokens"].append(sum(u.get(k, 0) or 0 for k in TOKEN_KEYS))
        if u.get("cost_usd") is not None:
            costs.append(u["cost_usd"])
            m["cost_usd"] += u["cost_usd"]
            m["priced"] += 1
            c["cost"].append(u["cost_usd"])
    starts = [ev.created_at for ev, _ in rows if ev.created_at]
    ends = [ev.finished_at for ev, _ in rows if ev.finished_at]
    wall = (max(ends) - min(starts)).total_seconds() if starts and ends else None
    avg_cost = sum(costs) / len(costs) if costs else None
    total_tok = sum(tok.values())
    return {
        "evaluations": len(rows),
        "ok": sum(ev.status == "ok" for ev, _ in rows),
        "errors": sum(ev.status == "error" for ev, _ in rows),
        "time": {
            "avg_s": _r(sum(durs) / len(durs)) if durs else None,
            "p50_s": _r(median(durs)) if durs else None,
            "p95_s": _pct(durs, 0.95),
            "max_s": _r(max(durs)) if durs else None,
            "total_model_s": _r(sum(durs)),
            "wall_clock_s": _r(wall),
            "per_minute": _r(len(rows) / wall * 60, 1) if wall else None,
        },
        "tokens": {
            "measured": measured_tok,
            **{k: tok[k] for k in TOKEN_KEYS},
            "total": total_tok,
            "avg_per_evaluation": round(total_tok / measured_tok) if measured_tok else None,
            "avg_input": round(tok["input_tokens"] / measured_tok) if measured_tok else None,
            "avg_output": round(tok["output_tokens"] / measured_tok) if measured_tok else None,
        },
        "cost": {
            "priced": len(costs),
            "unpriced": len(rows) - len(costs),
            "total_usd": _r(sum(costs), 6) if costs else None,
            "avg_per_evaluation_usd": _r(avg_cost, 6),
            "per_1000_usd": _r(avg_cost * 1000, 2) if avg_cost is not None else None,
            "usd_per_1m_tokens": _r(sum(costs) / total_tok * 1e6, 4) if costs and total_tok else None,
        },
        "by_model": [{"model": k, "count": v["count"], "priced": v["priced"], "cost_usd": _r(v["cost_usd"], 6),
                      "avg_s": _r(sum(v["dur"]) / len(v["dur"])) if v["dur"] else None,
                      "price_per_1m": price_for(k)} for k, v in by_model.items()],
        "by_channel": {k: {"count": v["count"], "avg_s": _r(sum(v["dur"]) / len(v["dur"])) if v["dur"] else None,
                           "avg_cost_usd": _r(sum(v["cost"]) / len(v["cost"]), 6) if v["cost"] else None,
                           "avg_tokens": round(sum(v["tokens"]) / len(v["tokens"])) if v["tokens"] else None}
                       for k, v in by_channel.items()},
    }

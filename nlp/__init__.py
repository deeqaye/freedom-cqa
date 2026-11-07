"""NLP package. The service calls nlp.get_evaluator()(conversation, checklist). See CONTRACT.md."""
from __future__ import annotations

import os


def get_evaluator():
    """Returns (evaluate_fn, name). Uses nlp/evaluator.py if it exists, else the stub.
    EVALUATOR=stub forces the stub; EVALUATOR=nlp fails loudly if evaluator.py is missing."""
    mode = os.getenv("EVALUATOR", "auto")
    if mode != "stub":
        try:
            from .evaluator import evaluate  # teammate's implementation
            return evaluate, "nlp"
        except ModuleNotFoundError as e:
            # Fall back only if evaluator.py itself is absent; a missing dependency inside it must surface.
            if mode == "nlp" or e.name != f"{__name__}.evaluator":
                raise
    from .stub import evaluate
    return evaluate, "stub"

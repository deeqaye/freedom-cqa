# NLP evaluator (`nlp/evaluator.py`)

**Model:** `gpt-6-luna` (OpenAI, `mode: external_api`)
**API key variable:** `OPENAI_API_KEY` (add to Render environment). Optional: `NLP_MODEL`, `OPENAI_BASE_URL`, `NLP_PRICE_IN` / `NLP_PRICE_OUT`.
**Cost of one evaluation (DEV, 65 dialogues, all LLM calls incl. reasoning translation):** average **$0.00134**; chat $0.00126, voice call $0.00233 (≈ $1.34 / 1000 dialogues; whole DEV $0.087). Prices: $0.10 / $0.50 per 1M input / output tokens.
**Time per evaluation:** avg 15.5 s (chat 14.2 s, call 31.7 s, p95 27.5 s); whole DEV in 270 s with 4 threads.
**Quality on DEV vs team labels (weighted agreement with checklist weights):** 95.77 overall, 96.80 synthetic chats, 83.40 real calls; final-score MAE 4.22; critical flag TP/FP/FN 5/3/0.

## What it does
- One LLM call per dialogue: 8 stages (least to most important, flag last), each with `reasoning` first, then value and `evidence_turns`. The prompt is built from `checklist["criteria"]` (description, na_condition, steps/step_labels, prompt_hint); a new/edited criterion gets a generic block from its own fields. Verified on `seed/checklist_compliance.json`.
- A mini translation call turns the English reasoning into Russian (`rationale`, required by the contract) and Kazakh (`rationale_kk`); English kept in `rationale_en`.
- Transcript preprocessing for calls (IVR menu, "client on hold" stretches); original `turn` numbers preserved.
- Thread-safe, SDK-level retries on rate limits, one extra attempt on invalid model output, exceptions on failure (no made-up zeros).

## Changed files
- `nlp/evaluator.py` (new), `nlp/README.md` (new: experiments, metrics, cost, time, train/dev split)
- `requirements.txt` (+ `openai>=1.50`), `.env.example` (+ `OPENAI_API_KEY`, `NLP_MODEL`)

## Checked
- `python -m nlp.check` — 5 DEV conversations OK; `pytest` — 33 passed; evaluator run on all 65 DEV dialogues, 4 threads, 0 errors.
- Control sets FBroker (10) and Swap (3) were labeled by Claude (`extras/gold_extra.json`, not human gold) and scored once: 95.85 weighted agreement on all 13 (FBroker 94.60, Swap 100). Results only under `runs/`, nothing written to `results/prod`.
- Not done yet: `scripts/export_results.py DEV --evaluate` (writes `results/dev/results.json`; one more API run ≈ $0.08).

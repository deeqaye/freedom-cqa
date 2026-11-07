# NLP ⇄ Service contract

> New here? Start with **[GUIDE.md](GUIDE.md)**: how the site calls your code, real input/output examples in `examples/`, and how to test.

The service handles everything except judging the conversation: storage, the API, the UI, appeals, scoring math, and the `results.json` export.
**The NLP part has one job:** read one conversation and the checklist, then return a raw value, a rationale and evidence turns for every criterion.

## What you must implement

File **`nlp/evaluator.py`** must contain:

```python
def evaluate(conversation: dict, checklist: dict) -> dict:
    ...
```

That is the only entry point. The service imports it, so it needs no HTTP server.
Until the file exists, the service uses `nlp/stub.py`, which is a rough keyword-based fake.
To check your code, run `python -m nlp.check` (see "Self-check" below).

## Input 1: `conversation`
This is the record exactly as the organizers' API returns it:
```json
{
  "conversation_id": "p1-ru-001",
  "channel": "agent chat",            // or "voice call"
  "language": "RU",                   // RU | KZ | EN
  "audio_url": null,                  // set only for calls
  "transcript": [
    {"turn": 1, "timestamp": "00:00", "speaker": "client", "text": "..."},
    {"turn": 2, "timestamp": "00:02", "speaker": "bot",    "text": "..."}
  ]
}
```
- **`turn`** is added by the service. It is a 1-based number over the full transcript (client, operator, bot and system messages all count). **Use it for `evidence_turns`.**
- Speakers are `client`, `operator`, `bot` and `system`. **Score the operator only.** Bot and system messages are context: for example, the client may have explained the issue to the bot before the handoff, and "Эскалация на оператора" marks when the operator joins.
- Chat timestamps are `MM:SS`. Call timestamps are ISO 8601. Call transcripts come from speech recognition, so expect garbled words and `[Имя скрыто]`.

## Input 2: `checklist`
```json
{
  "id": "chat-quality", "version": 3,
  "criteria": [
    {
      "id": "consultation",
      "section": "Безопасность и решение",
      "title": "Корректная и полная консультация",
      "type": "scale",                      // "binary" | "scale" | "flag"
      "steps": [0, 5, 10, 15, 20],          // only for scale
      "step_labels": {"20": "...", "15": "..."},
      "weight": 20,
      "na_allowed": true,
      "description": "When to answer yes / how to grade",
      "na_condition": "When N/A applies",
      "prompt_hint": "Extra instruction written by the admin in the UI"
    }
  ]
}
```

> ⚠️ **Build the prompt from these fields. Do not hard-code the 8 criteria.**
> At the control check the organizers will replace a criterion through the UI. Your code has to evaluate whatever list it receives, including a new `id`, new wording and a new scale. Admins can also add a `prompt_hint` to any criterion.

## Output (required)
```json
{
  "criteria": [
    {
      "criterion_id": "consultation",
      "value": 15,
      "rationale": "Основной вопрос решён, не уточнён срок ответа.",
      "evidence_turns": [10, 12],
      "checked_turns": [10, 14],
      "na_reason": null
    }
  ],
  "model": {"mode": "external_api", "name": "claude-sonnet-5-5"},
  "usage": {"input_tokens": 3100, "output_tokens": 600, "cost_usd": 0.012}
}
```

| field | required | rule |
|---|---|---|
| `criterion_id` | yes | Every checklist criterion `id` **exactly once**. No extras. |
| `value` | yes | `binary` / `flag` → `true` or `false`. `scale` → **one of `steps`**, for example `7`, not `6` or `"7"`. `null` = N/A, **only if `na_allowed` is true**. |
| `rationale` | yes | 1–2 short sentences in Russian, for example: «Завершение — Нет. Оператор закрыл чат без прощания.» |
| `evidence_turns` | yes | 1-based `turn` numbers that support the verdict. For a skipped action, give the turn where the action was expected. For N/A, give the turn that shows the N/A condition is met. Do not return an empty list. |
| `checked_turns` | no | `[from, to]`, the range examined. Useful for "No, the action was missing". |
| `na_reason` | when `value` is null | The N/A condition that is met. |
| `model` | yes | `mode`: `local` / `external_api` / `hybrid`. `name`: the real model name(s). |
| `usage` | recommended | Tokens and cost. The guide requires the cost of one evaluation. Sum over **all** LLM calls made for this conversation (retries included). Keys: `input_tokens`, `output_tokens`, optional `cache_read_input_tokens`, `cache_creation_input_tokens`, `cost_usd`. If `cost_usd` is left out, the service computes it from `model.name` and its price table. Time is measured by the service. |

`flag` criteria (the `critical` one) carry **no points**. `true` means a gross violation was found: insulting the client, offering a paid service that bypasses the company, or disclosing confidential data. Offering it is enough to set the flag.

## What you do NOT do
- **No weights, totals, N/A redistribution or rounding.** The service computes `final_score` deterministically.
- **No retries for invalid output past one attempt, no database, no JSON export.**
- **To signal failure, raise an exception.** The service records it as `status: "error"` with your message, as the organizers require. Never return made-up zeros.

## Validation the service applies
If you return a missing or duplicate criterion, an unknown id, a value outside `steps`, or `null` where N/A is not allowed, the evaluation is rejected with `status: "error"`. Run the self-check before handing over.

## Self-check
```bash
python -m nlp.check                   # runs your evaluate() on 5 DEV conversations and validates the output
python -m nlp.check p1-ru-001 p4-ru-002
python -m nlp.check --checklist compliance   # second checklist: different ids and scale
python -m nlp.check --all                     # all 65 DEV conversations
```

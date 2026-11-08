# Evaluation pipeline: stages (English prompt `prompts/v5_en_wasc.md`)

One model call per dialogue. The model goes through 8 stages in a fixed order; **every stage first writes `reasoning` (1-2 sentences, English, citing turn numbers), then the `value`, then `evidence_turns`**. The total score is NOT computed by the model (code does the weighting).

**Stage order = from least to most important (by checklist weight), the hard-violation flag last:**

| # | stage | weight | what the model does | reasoning must say |
|---|---|---|---|---|
| 1 | closure | 5 | Look at the end of the dialogue: did the operator summarize/offer help AND say goodbye? Or did the client/system/connection end it first (N/A)? A formal goodbye over an unanswered client question = No. | which turn is the ending, who ended it |
| 2 | contact | 10 | First operator reply to the client: greeting AND own name? (Garbled by speech recognition = count if meaning is there.) | quote/turn of greeting and of the name |
| 3 | discovery | 15 | Was information missing? Did the operator ask a relevant question, without re-asking what the client already told the bot? N/A if the request was clear and the operator just answered. | what was missing/known, which question |
| 4 | empathy | 15 | Polite? If the client showed dissatisfaction/confusion/inconvenience, did the operator react to that exact problem? Do not demand sympathy phrases otherwise. | the client's expressed feeling and the reaction (or its absence) |
| 5 | dialogue | 15 | Clear and ordered answers, no ignored questions, warned about waiting. Re-asks caused by a bad phone line are not the operator's fault. | which failure (if any) hindered the client |
| 6 | identification | 20 | Was account-specific data disclosed / a protected action done? Was identity confirmed in the chat BEFORE that? N/A for general questions. | what data/action, where confirmation is (or missing) |
| 7 | consultation | 20 | List what the client asked; check each answer for correctness and completeness; scale 0/5/10/15/20. | each question and whether answered |
| 8 | critical | flag | Scan every operator turn for: insult; offer of a paid/personal service outside the company; disclosure of confidential data to an unverified client. | the exact violating turn, or why none |

Cross-cutting rules (in the prompt): bot/system lines are context (the client often explained the problem to the bot, the operator knows it); calls are noisy speech recognition (judge by meaning); IVR menu lines and "operator talking to a colleague while the client is on hold" are relabeled by `prep.py` and not judged as dialogue with the client; `false` = action was needed but missed, `null` = N/A condition holds.

## Why this order (analysis)
- Measured: stage order does **not** change quality beyond noise (6 repeats each, weighted agreement 94.6 / 95.5 / 95.5 for dependency / checklist / least-to-most-important order; noise sd ≈ 0.6). So the order was chosen by the requested logic: cheap objective checks first, the heavy judgment criteria (identification, consultation) later when the model has already read the whole dialogue three times, and the critical flag last as a final scan.
- The only measured effect of English vs Russian prompt: none (95.5 vs 95.2, noise sd 0.7).
- Largest remaining errors (points lost out of 100): discovery ~0.9, consultation ~0.7, dialogue ~0.9, empathy ~0.8, identification ~0.6, closure ~0.45, contact 0.15.

## Cost (Luna, gpt-6-luna at $0.10 / $0.50 per 1M tokens)
about $0.93 per 1000 dialogues ($0.00093 per dialogue); ~5.3k input tokens (rules + 4 examples) + ~0.9k output tokens. Terra is ~8x more expensive without better accuracy (measured earlier).

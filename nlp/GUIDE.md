# NLP guide: how the site uses your evaluator

This guide is the walkthrough. **[CONTRACT.md](CONTRACT.md)** is the exact spec of the input and output. Your work is one file, `nlp/evaluator.py`, with one function:

```python
def evaluate(conversation: dict, checklist: dict) -> dict
```

Everything else is already built and calls this function.

## 1. What happens around your function

```
 organizers' API / JSON file
          │  "⤓ Загрузить набор"  (POST /api/ingest, /api/ingest/url, /api/conversations/upload)
          ▼
 ┌────────────────────┐   adds "turn" (1-based) to every message, stores it
 │  conversations DB  │
 └─────────┬──────────┘
           │  "Оценить набор" / "Оценить" / "Запустить оценку"   (POST /api/evaluations)
           ▼
 ┌──────────────────────────────────────────────────────────────┐
 │ service: thread pool, EVAL_WORKERS=4 conversations at a time │
 │   for each conversation:                                     │
 │     out = nlp.evaluator.evaluate(conversation, checklist)  ◄── YOUR CODE
 │     validate out  ──invalid──► status "error" (with message) │
 │     compute score (weights, N/A, rounding)  ── service only  │
 │     store values, rationale, evidence, model, usage, time    │
 └─────────┬────────────────────────────────────────────────────┘
           ▼
 UI card · appeals · analytics · cost panel · results/dev|prod/results.json
```

- **When it's called:** each time someone clicks an evaluate button, calls `POST /api/evaluations`, or runs `scripts/export_results.py --evaluate`. Each call handles **one conversation**.
- **Concurrency:** up to **4 calls run at the same time in threads**. Keep `evaluate` thread-safe, with no shared mutable globals. One shared API client is fine: the Anthropic and OpenAI SDK clients are thread-safe.
- **Which checklist you get:** the active version of the checklist chosen in the UI. There are **two** right now:
  - `chat-quality`: the organizers' checklist, which is the one that goes into `results.json`.
  - `compliance`: a mock checklist with different ids, weights and a scale `0/10/18/25`.
  
  At the control check the organizers will edit a criterion in the UI, so your code must work from whatever `checklist["criteria"]` contains.
- **Time and cost:** the service measures the time around your call. Return tokens in `usage`; the service fills `cost_usd` from its price table if you leave it out.
- **Failure:** raise an exception with a clear message. The UI shows "Оценка не выполнена: <your message>", and `results.json` gets `status: "error"`, as the rules require. Never return made-up values.

## 2. Input: real example
**[examples/p1-ru-001.input.json](examples/p1-ru-001.input.json)** is the exact `{conversation, checklist}` the service passes for DEV chat `p1-ru-001`. You can produce such a file for any conversation (see §5).

The conversation in short. `turn` is what you cite in `evidence_turns`:
```
 1 00:00 client   Где посмотреть мой тариф? В приложении не нахожу.
 2 00:02 bot      Здравствуйте! Я AIM, AI-ассистент Freedom Broker …
 …
 9 00:38 system   Эскалация на оператора.          ← operator joins after this
10 01:15 operator Здравствуйте! Меня зовут Алина. В веб-версии откройте вкладку «Кабинет». …
11 01:28 client   Нашла, спасибо.
12 02:04 operator Пожалуйста. Хорошего вечера!
```

What the data looks like:

| | DEV set |
|---|---|
| conversations | 65: 60 chats (`agent chat`), 5 calls (`voice call`) |
| languages | RU 35, KZ 15, EN 15. Write the rationale in **Russian** whatever the dialog language. |
| length | up to 115 messages, about 2.5k characters of transcript on average |
| speakers | `client`, `operator`, `bot`, `system`. **Grade the operator only.** The bot and system messages are context. |
| chats | `timestamp` is `MM:SS` from the start |
| calls | `timestamp` is ISO 8601. The text comes from speech recognition and is noisy, with names hidden as `[Имя скрыто]`. System lines mark recording start, pause and resume. You can ignore `audio_url`; the service plays the audio. |

Each criterion carries everything you need for the prompt:
- `title`
- `description`: when "yes" applies and how to grade
- `type` and `steps`
- `step_labels`: what each scale step means
- `na_allowed` and `na_condition`: when N/A applies
- `prompt_hint`: an extra instruction the admin types in the UI. **Always include it.**

## 3. Output: real example
**[examples/p1-ru-001.output.json](examples/p1-ru-001.output.json)** is a correct answer for that conversation. The service scores it **100.00**: discovery and identification are N/A, so their weight is redistributed. It shows:
- every criterion id exactly once, in any order
- `value`:
  - binary and flag criteria take `true` / `false`
  - scale criteria take **a number from `steps`**
  - `null` means N/A, and only where `na_allowed` is true, with `na_reason`
- `evidence_turns`: never empty. For a "No", cite the turn where the action was expected; for N/A, cite the turn that shows why it doesn't apply.
- `model`: `{mode, name}`. This goes straight into `results.json`.
- `usage`: tokens, which the service turns into $0.0133 for `claude-sonnet-5-5`.

## 4. Where each output field shows up

| your field | UI | results.json |
|---|---|---|
| `value` | criterion row (Да / Нет / N/A / step), section points, total ring | `criteria[].value` |
| `rationale` | text under each criterion; the "Почему снижена оценка" list | `criteria[].rationale` |
| `evidence_turns` | "Перейти к фрагменту": scrolls to and highlights the turns; for calls it also seeks the audio | `criteria[].evidence_turns` |
| `checked_turns` | highlighted range when the answer is "action was missing" | — |
| `na_reason` | shown for N/A criteria | — |
| `model.name` | card header; cost panel by model | `model.name` |
| `usage` | card header (`3 400 → 650 токенов · $0.0133`); Аналитика → Стоимость обработки | — |

Operators can appeal any criterion and a lead can override it. The service keeps your original value, and `results.json` always uses yours.

## 5. How to test

```bash
uv venv --python 3.12 .venv && uv pip install -p .venv -r requirements.txt   # once

.venv/bin/python -m nlp.check                          # 5 mixed DEV conversations (RU/KZ/EN chat + a call)
.venv/bin/python -m nlp.check p4-ru-002 p1-kz-003      # chosen ones
.venv/bin/python -m nlp.check --checklist compliance   # the other checklist: proves nothing is hard-coded
.venv/bin/python -m nlp.check --all                    # all 65, prints avg time per conversation
.venv/bin/python -m nlp.check p1-ru-001 --dump /tmp/x  # writes <id>.input.json + <id>.output.json
```

`OK` means the output passes the same validation as the service. `FAIL` gives the reason, for example `value 6 not in steps [0, 4, 7, 10]` or `missing criteria: closure`.

**Full app with your evaluator:**
```bash
EVALUATOR=nlp .venv/bin/uvicorn app.main:app --app-dir backend --reload   # http://localhost:8000
```
The sidebar shows **«Оценщик: nlp»**. If it says `stub`, `nlp/evaluator.py` wasn't found. Open a conversation and click **Оценить**, or select the DEV set and click **Оценить набор**.
- `EVALUATOR=nlp` fails loudly if your file can't be imported, for example because of a missing package.
- The default, `auto`, uses your file when it exists and the stub otherwise.

**Rehearse the criterion swap:** go to Чек-листы, change a criterion's id, wording or scale, and click "Сохранить новую версию". Then run the evaluation again. It should still validate.

## 6. Shipping it
1. Put new packages in **`requirements.txt`**, e.g. `anthropic`.
2. Read API keys **from environment variables**, e.g. `ANTHROPIC_API_KEY`. Never commit a key: `.env` is gitignored. Ask me to add the key on Render (Environment → Add variable).
3. Push to a branch and open a PR. Render redeploys `main` automatically, so I'll merge after `nlp.check --all` passes.
4. Then we regenerate `results/dev/results.json`:
   ```bash
   .venv/bin/python scripts/export_results.py DEV --evaluate --version 1
   ```
   It also prints time, tokens and cost per conversation for the README.

## 7. Practical tips
- **Speed:** 65 conversations at 4 at a time. Aim for under about 20 s per conversation, and pass a client `timeout`. For the control set (10 conversations at hour 23) we want everything done in a few minutes.
- **Model calls:**
  - Make one call per conversation that grades all criteria, with the transcript formatted as `[turn] speaker: text`. That's cheaper and keeps the evidence consistent.
  - Use structured outputs or JSON-schema tool output to get exact JSON.
  - Repair or validate it yourself once; if it's still invalid, raise.
- **Bot vs operator:**
  - The first greeting is usually the **bot's**; it doesn't count for `contact`.
  - The client may have explained the issue to the bot before the handoff, so `discovery` can be N/A.
- **`critical`:** offering a paid service outside the company or a personal transfer is enough to set it. It's a flag with no points: the service shows it separately and doesn't zero the score.
- **Language:** KZ and EN conversations are graded the same way; only the rationale has to be in Russian.

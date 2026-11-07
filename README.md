# CQA — Conversation Quality Analytics

This prototype scores operator conversations (chats and calls, in RU, KZ and EN) against a configurable checklist. It shows the evidence behind each score and supports appeals and review.

- **Service** (`backend/`): FastAPI and SQLAlchemy. It handles storage, versioned checklists, deterministic scoring, the evaluation queue and the `results.json` export.
- **NLP** (`nlp/`): an LLM evaluator behind one function. See **[nlp/CONTRACT.md](nlp/CONTRACT.md)**.
- **UI** (`frontend/`): plain HTML, CSS and JavaScript, served at `/ui/`.

## Run

```bash
cp .env.example .env            # set ORG_API_URL (organizer GET url without &group_id=...)
docker compose up --build       # http://localhost:8000  (API docs: /docs)
```
Without Docker:
```bash
uv venv --python 3.12 .venv && uv pip install -p .venv -r requirements.txt
.venv/bin/uvicorn app.main:app --app-dir backend --reload
```
On first start the service seeds the checklists in `seed/checklist_*.json` and every dataset snapshot in `data/*.json`.
Two checklists ship: the organizers' `chat-quality` (used for `results.json`) and a mock `compliance` checklist
(security, risk disclosure, next step) for comparing how the same conversations score under different checklists.

## Deploy (Render)
1. Push this repo to GitHub.
2. In Render, go to **New + → Blueprint**, pick the repo, and Render reads `render.yaml`. It creates a free Docker web service and a free Postgres.
3. Set the `ORG_API_URL` secret when prompted. It's only needed for fetching new datasets (the control set); DEV is already in `data/DEV.json`.
4. On first start the service seeds the checklist and DEV, and imports `results/*/results.json`, so scores show without re-running the model.

The free web service sleeps after 15 minutes idle, so open it about a minute before judging. Each push to `main` redeploys automatically.
Without Postgres (`DATABASE_URL` unset), it uses SQLite in `data/cqa.db`.

## API, as used by the judges
| | |
|---|---|
| `POST /api/ingest?group_id=X` | fetch a dataset from the organizers' API |
| `POST /api/ingest/url` `{"url": "<full GET link>"}` | fetch a dataset from a full organizer link (https, organizer domain only) |
| `POST /api/conversations/upload` | upload a dataset JSON file (API response, `{records}` or a list) |
| `GET /api/conversations` · `/api/conversations/{id}` | list and card (transcript with 1-based `turn`) |
| `GET/PUT /api/checklists/chat-quality` | read the checklist / save a new version (header `X-Role: admin\|lead`) |
| `POST /api/evaluations` `{"group_id":"DEV"}` or `{"conversation_ids":[...], "wait":true}` | run an evaluation |
| `GET /api/conversations/{id}/evaluation?checklist_id=` | per-criterion value, points, rationale, evidence, sections, total (latest, or latest under one checklist) |
| `GET /api/conversations/{id}/evaluations` | this conversation's score under each checklist version |
| `GET /api/stats/compare?group_id=` | the same conversations under each checklist: averages, critical count, biggest differences |
| `POST /api/appeals` · `POST /api/appeals/{id}/decision` (header `X-Role: lead\|admin`) | dispute a criterion / accept or reject; the total is recalculated and the original is kept |
| `GET /api/stats/overview?period=week\|month&checklist_id=` · `/api/stats/operators/{name}` | quality stats |
| `GET /api/stats/cost?group_id=&ids=` | processing time and cost: per conversation, per 1000, per 1M tokens, by channel and model |
| `GET /api/audio/{conversation_id}` | call recording (cached, seekable) |
| `GET /api/export/{group_id}?checklist_version_id=` | `results.json`, schema 1.0 |

## Roles
The UI page **Справочник** (`#/help`) lists what each role can do. In short: an operator views results and files appeals; a lead (главный специалист) also edits checklists and decides appeals; an admin can also clear and reload data. The demo has no login: the role switcher sends `X-Role`, and the server checks it on actions that change data.

## Scoring
- "Yes" earns the full weight and "No" earns 0. A scale value earns `weight × value / top step`.
- N/A criteria are excluded and their weight is redistributed: `final = earned / applicable weight × 100`, rounded to 2 decimals (half up).
- `critical` is reported as a separate flag and does not zero the score.
- See `backend/app/services/scoring.py` and its tests (the appendix example gives 85.38).

## Processing cost
Each evaluation stores its time (`duration_s`, the evaluator call only) and `usage` (tokens, `cost_usd`).
If the evaluator reports tokens without a cost, the service prices them from the table in
`backend/app/services/cost.py` (USD per 1M tokens; extend it with env `MODEL_PRICES='{"model": {"input": 1, "output": 5}}'`).
- UI: the card header shows time, tokens and cost of the evaluation; a batch run ends with a summary line; **Аналитика** (admin) has a "Стоимость обработки" panel.
- API: `GET /api/stats/cost?ids=<batch ids>` gives one run, including its wall-clock time and throughput; `?group_id=DEV` gives the latest evaluation of each conversation.
- `scripts/export_results.py ... --evaluate` prints the same summary.

| DEV (65 conversations) | value |
|---|---|
| model | _TBD_ |
| time per conversation (avg / p95) | _TBD_ |
| tokens per conversation (in → out) | _TBD_ |
| cost per conversation / per 1000 | _TBD_ |

## Submitting results
```bash
.venv/bin/python scripts/export_results.py DEV --evaluate                 # -> results/dev/results.json
.venv/bin/python scripts/export_results.py <PROD_GROUP> --prod --evaluate --version 1 # -> results/prod/results.json (10)
```
The results format requires the original 8 criterion codes. If a criterion has been swapped in the UI, pass `--version 1`. The script refuses to validate an export with different codes.

## Tests
```bash
.venv/bin/python -m pytest        # scoring + API
.venv/bin/python -m nlp.check     # validates the NLP evaluator output against the contract
```

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
On first start the service seeds the default checklist and every dataset snapshot in `data/*.json`.

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
| `POST /api/conversations/upload` | upload a dataset JSON file |
| `GET /api/conversations` · `/api/conversations/{id}` | list and card (transcript with 1-based `turn`) |
| `GET/PUT /api/checklists/chat-quality` | read the checklist / save a new version (header `X-Role: admin\|lead`) |
| `POST /api/evaluations` `{"group_id":"DEV"}` or `{"conversation_ids":[...], "wait":true}` | run an evaluation |
| `GET /api/conversations/{id}/evaluation` | per-criterion value, points, rationale, evidence, sections, total |
| `POST /api/appeals` · `POST /api/appeals/{id}/decision` (header `X-Role: lead\|admin`) | dispute a criterion / accept or reject; the total is recalculated and the original is kept |
| `GET /api/stats/overview?period=week\|month` · `/api/stats/operators/{name}` | quality stats |
| `GET /api/audio/{conversation_id}` | call recording (cached, seekable) |
| `GET /api/export/{group_id}?checklist_version_id=` | `results.json`, schema 1.0 |

## Scoring
- "Yes" earns the full weight and "No" earns 0. A scale value earns `weight × value / top step`.
- N/A criteria are excluded and their weight is redistributed: `final = earned / applicable weight × 100`, rounded to 2 decimals (half up).
- `critical` is reported as a separate flag and does not zero the score.
- See `backend/app/services/scoring.py` and its tests (the appendix example gives 85.38).

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

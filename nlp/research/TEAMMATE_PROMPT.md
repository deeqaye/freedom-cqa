# Prompt for the teammate's Claude Code (paste into Claude Code opened in the `freedom-cqa` repo)

```
Context: repo freedom-cqa (FastAPI service + nlp/evaluator.py). The NLP evaluator (OpenAI gpt-6-luna, env OPENAI_API_KEY) is already written; do NOT modify nlp/evaluator.py.
The organizers released the control set FBroker (10 chats). Goal: produce results/prod/results.json for it and push it to Git BEFORE THE STOP CODE (we have 1 hour total including fetching, scoring, validation and the push; local save or commit without push does not count).
A second set, Swap (3 chats), must only be fetched/saved. DO NOT evaluate Swap and DO NOT add it to results/prod.

Do this step by step and report what you see after each step:
0. Preconditions: .venv exists (Python 3.12), .env contains OPENAI_API_KEY and ORG_API_URL (the organizers' GET link WITHOUT the group_id parameter), EVALUATOR is unset or "auto", the branch contains nlp/evaluator.py. Never print, log or commit the API key; .env must not be staged.
1. Start the service: .venv/bin/uvicorn app.main:app --app-dir backend  (in the background). Fetch the sets into the DB:
     curl -X POST "localhost:8000/api/ingest?group_id=FBroker"   -> expect 10 conversations (ids p2-ru-001..004, p2-kz-001..004, p2-en-001..002; all "agent chat")
     curl -X POST "localhost:8000/api/ingest?group_id=Swap"      -> expect 3 conversations (p3-ru-001, p3-kz-001, p3-en-001); ingest only.
2. Score FBroker with the ORIGINAL checklist (version 1, the 8 default criteria; never the "compliance" checklist):
     .venv/bin/python scripts/export_results.py FBroker --prod --evaluate --version 1
   Expect: "wrote results/prod/results.json: 10 records (10 ok)", exit code 0, no lines starting with "!". Note the printed time / tokens / cost summary (expected ~$0.013 total, ~1 minute with 4 workers).
3. Validate the file yourself: valid UTF-8 JSON without comments or trailing commas; exactly 10 results; conversation_ids exactly equal to the API ids, no duplicates; every record status "ok" (if one is "error", read the message, fix the cause such as a rate limit or missing key and rerun that evaluation; NEVER fabricate zeros or edit values by hand); every record has all 8 criterion codes once (contact, discovery, identification, consultation, empathy, dialogue, closure, critical), non-empty evidence_turns in 1..N, Russian rationale, score.final_score and score.critical_flag present.
4. Optional (30 seconds): fill the "Processing cost" table in README.md for DEV with: model gpt-6-luna; time per conversation avg 15.5 s / p95 27.5 s; tokens per conversation 5597 in -> 1560 out; cost per conversation $0.00134 / per 1000 $1.34 (these come from our DEV run).
5. Git: `git status`, make sure only results/prod/results.json (and the optional README change) are staged. Commit with the message "FBroker prod results". Pushing to main redeploys the live site and results/prod is a graded file, so ASK ME which branch to push to before pushing; after my answer push, then show me `git log -1` and the remote branch name. Confirm the file is visible in the remote repo.
Do not touch anything else. If anything is unclear or a step fails twice, stop and ask me.
```

## Plain-language checklist for the teammate (same thing, short)
1. Make sure `.env` has `OPENAI_API_KEY` and `ORG_API_URL` (organizers' link **without** `group_id`).
2. Run the service, `POST /api/ingest?group_id=FBroker` (10 chats) and `group_id=Swap` (3 chats, save only).
3. `scripts/export_results.py FBroker --prod --evaluate --version 1` -> `results/prod/results.json` (10 records, all `ok`).
4. Validate (10 ids = API ids, no errors, 8 criteria each) and **push** before the stop code.
5. Do **not** score Swap and do not add it to `results/prod` until the organizers send the extra instruction.

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import seed
from .config import FRONTEND_DIR, SEED_ON_START
from .db import Base, SessionLocal, engine
from .routers import appeals, audio, checklists, conversations, evaluations, stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    if SEED_ON_START:
        with SessionLocal() as db:
            seed.run(db)
    yield


app = FastAPI(title="CQA — Conversation Quality Analytics", version="0.1.0", lifespan=lifespan,
              description="Checklist-based operator quality scoring. Interactive docs: /docs")
# Allow embedding the UI elsewhere (e.g. as a Dynamics 365 HTML web resource).
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(conversations.router)
app.include_router(checklists.router)
app.include_router(evaluations.router)
app.include_router(appeals.router)
app.include_router(stats.router)
app.include_router(audio.router)


@app.get("/api/health", tags=["meta"])
def health():
    from nlp import get_evaluator
    return {"ok": True, "evaluator": get_evaluator()[1]}


if FRONTEND_DIR.exists() and any(FRONTEND_DIR.iterdir()):
    app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/ui/" if FRONTEND_DIR.exists() and any(FRONTEND_DIR.iterdir()) else "/docs")

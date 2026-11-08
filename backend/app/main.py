from __future__ import annotations

import hashlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import seed
from .config import FRONTEND_DIR, SEED_ON_START
from .db import Base, SessionLocal, engine
from .routers import admin, appeals, audio, checklists, conversations, evaluations, stats

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


@app.middleware("http")
async def no_stale_ui(request, call_next):
    """UI files are ES modules that import each other: after a deploy a browser must not mix cached old files with
    new ones (a missing export blanks the page). no-cache = always revalidate (ETag -> cheap 304 if unchanged)."""
    resp = await call_next(request)
    path = request.url.path
    if path.startswith("/ui/v/"):     # content-addressed (see ASSET_V): safe to cache forever
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/ui"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp

app.include_router(conversations.router)
app.include_router(checklists.router)
app.include_router(evaluations.router)
app.include_router(appeals.router)
app.include_router(stats.router)
app.include_router(audio.router)
app.include_router(admin.router)


@app.get("/api/health", tags=["meta"])
def health():
    from nlp import get_evaluator
    return {"ok": True, "evaluator": get_evaluator()[1]}


def _asset_version() -> str:
    """Hash of every frontend file: changes on each deploy that touches the UI."""
    h = hashlib.sha1()
    for p in sorted(FRONTEND_DIR.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(FRONTEND_DIR)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


if FRONTEND_DIR.exists() and any(FRONTEND_DIR.iterdir()):
    # Cache busting: index.html points CSS/JS at /ui/v/<hash>/..., and ES modules import each other by relative
    # path, so after a deploy the browser fetches a whole new, consistent set instead of mixing cached old files.
    ASSET_V = _asset_version()

    @app.get("/ui/", include_in_schema=False)
    @app.get("/ui/index.html", include_in_schema=False)
    def ui_index():
        html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        html = html.replace('href="css/', f'href="v/{ASSET_V}/css/').replace('src="js/', f'src="v/{ASSET_V}/js/')
        return HTMLResponse(html)

    app.mount(f"/ui/v/{ASSET_V}", StaticFiles(directory=FRONTEND_DIR), name="ui-versioned")
    app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/ui/" if FRONTEND_DIR.exists() and any(FRONTEND_DIR.iterdir()) else "/docs")

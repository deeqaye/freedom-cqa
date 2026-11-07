from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
SEED_DIR = ROOT / "seed"
RESULTS_DIR = ROOT / "results"
FRONTEND_DIR = ROOT / "frontend"

DATA_DIR.mkdir(exist_ok=True)

ORG_API_URL = os.getenv("ORG_API_URL", "")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'cqa.db'}")
# Render/Heroku-style URLs -> SQLAlchemy + psycopg 3 driver
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]
EVAL_WORKERS = int(os.getenv("EVAL_WORKERS", "4"))
TEAM_NAME = os.getenv("TEAM_NAME", "Freedom HT")
SEED_ON_START = os.getenv("SEED_ON_START", "1") == "1"
SEED_RESULTS = os.getenv("SEED_RESULTS", "1") == "1"  # import committed results/*/results.json on a fresh DB

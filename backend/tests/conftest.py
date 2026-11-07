import os
import tempfile

# Isolated DB and stub evaluator for tests; must be set before the app is imported.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["EVALUATOR"] = "stub"
os.environ["SEED_RESULTS"] = "0"
os.environ["SNAPSHOT_DIR"] = tempfile.mkdtemp()

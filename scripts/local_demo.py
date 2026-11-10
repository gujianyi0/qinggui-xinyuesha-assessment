"""Run a local mock API with migrations; SQLite/test vectors are smoke tests only."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--faults", action="store_true")
    parser.add_argument("--database", type=Path, default=ROOT / ".local/demo.sqlite3")
    args = parser.parse_args()
    database = args.database.resolve()
    if not database.is_relative_to(ROOT):
        parser.error("demo database must stay inside this assessment project")
    database.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(DATABASE_URL=f"sqlite+aiosqlite:///{database.as_posix()}", MODEL_MODE="mock",
               EMBEDDING_MODE="test", CREATE_SCHEMA="false", SEED_USERS="true",
               ENABLE_TEST_FAULTS=str(args.faults).lower(),
               REDIS_URL="redis://127.0.0.1:1/0")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True)
    subprocess.run([sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(args.port)], cwd=ROOT, env=env, check=True)


if __name__ == "__main__":
    main()

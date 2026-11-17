import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[1]


def test_migration_upgrade_downgrade_on_disposable_database(tmp_path):
    database = tmp_path / "migration.sqlite3"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database.as_posix()}"}
    for target in [("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")]:
        subprocess.run([sys.executable, "-m", "alembic", *target], cwd=ROOT, env=env, capture_output=True, check=True)
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        assert {"jobs", "outbox", "feedback", "published_indexes", "usage_records"} <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

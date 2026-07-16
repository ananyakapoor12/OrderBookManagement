"""
conftest.py — shared pytest fixtures.

Each test gets its own isolated SQLite database file in a tmp_path directory.
We monkeypatch config.DATABASE_URL before any test logic runs so that all
module-level imports that reference it pick up the test path dynamically.
"""
import pytest
import app.core.config as config
from app.infra.db import init_db


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    """
    Point every test at a fresh, temporary SQLite database.
    autouse=True means this fixture runs for EVERY test automatically.
    """
    db_path = str(tmp_path / "test_oms.db")
    monkeypatch.setattr(config, "DATABASE_URL", db_path)

    # Also patch the db module's reference so get_connection() uses the test DB
    import app.infra.db as db_mod
    monkeypatch.setattr(db_mod, "DATABASE_URL", db_path, raising=False)

    init_db()
    yield

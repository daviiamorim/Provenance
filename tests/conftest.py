"""Shared test fixtures.

Database tests require TEST_DATABASE_URL to be set (see .env.example).
If a .env file is present in the project root it is loaded automatically,
so running `uv run pytest` after copying .env.example works without any
manual environment variable setup.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

# Load .env from project root if present — setdefault so explicit env vars win.
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for _raw in _env_file.read_text(encoding="utf-8").splitlines():
        _raw = _raw.strip()
        if _raw and not _raw.startswith("#") and "=" in _raw:
            _k, _, _v = _raw.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

_TEST_DB_VAR = "TEST_DATABASE_URL"


@pytest.fixture(scope="session")
def test_db_url() -> str:
    url = os.environ.get(_TEST_DB_VAR, "")
    if not url:
        pytest.skip(f"Set {_TEST_DB_VAR} to run database tests")
    return url


@pytest.fixture
def db_conn(
    test_db_url: str,
) -> Generator[psycopg.Connection[dict[str, Any]], None, None]:
    """Per-test psycopg3 connection wrapped in a transaction that always rolls back.

    This implements the BEGIN/ROLLBACK isolation pattern: every test starts
    with an empty-ish database and leaves no residue for the next test.
    """
    conn: psycopg.Connection[dict[str, Any]] = psycopg.connect(
        test_db_url, row_factory=dict_row, autocommit=False
    )
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()

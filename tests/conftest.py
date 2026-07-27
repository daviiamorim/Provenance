"""Shared test fixtures.

Database tests require TEST_DATABASE_URL to be set (see .env.example).
They are automatically skipped when that variable is absent, so the existing
unit-test suite continues to work without Docker.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

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

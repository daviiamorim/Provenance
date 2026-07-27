"""FastAPI dependencies."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

import psycopg
from psycopg.rows import dict_row

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/data_observatory",
)


def get_db() -> Generator[psycopg.Connection[dict[str, Any]], None, None]:
    """Yield a psycopg3 connection, committing on success, rolling back on error."""
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn

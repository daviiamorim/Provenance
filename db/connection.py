"""psycopg3 connection factory."""

from __future__ import annotations

import os
from typing import Any

import psycopg
from psycopg.rows import dict_row

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/data_observatory",
)

type Conn = psycopg.Connection[dict[str, Any]]


def get_connection(url: str | None = None) -> Conn:
    """Open a new psycopg3 connection using dict_row factory."""
    return psycopg.connect(url or DATABASE_URL, row_factory=dict_row)

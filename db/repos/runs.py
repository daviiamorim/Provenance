"""Run repository."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from db.connection import Conn


def upsert(
    conn: Conn,
    run_id: str,
    dataset_id: str,
    producer_versions: dict[str, str],
    config_digest: str,
) -> None:
    conn.execute(
        """
        INSERT INTO runs (id, dataset_id, producer_versions, config_digest)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (run_id, dataset_id, Jsonb(producer_versions), config_digest),
    )


def get(conn: Conn, run_id: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM runs WHERE id = %s", (run_id,))
    return cur.fetchone()


def list_by_dataset(conn: Conn, dataset_id: str) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT * FROM runs WHERE dataset_id = %s ORDER BY created_at DESC",
        (dataset_id,),
    )
    return cur.fetchall()

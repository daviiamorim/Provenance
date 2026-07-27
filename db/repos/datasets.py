"""Dataset repository."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from db.connection import Conn


def upsert(
    conn: Conn,
    dataset_id: str,
    manifest: list[dict[str, str]],
    upload_dir: str,
) -> None:
    conn.execute(
        """
        INSERT INTO datasets (id, manifest, upload_dir)
        VALUES (%s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (dataset_id, Jsonb(manifest), upload_dir),
    )


def get(conn: Conn, dataset_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM datasets WHERE id = %s",
        (dataset_id,),
    )
    return cur.fetchone()


def list_all(conn: Conn) -> list[dict[str, Any]]:
    cur = conn.execute("SELECT * FROM datasets ORDER BY created_at DESC")
    return cur.fetchall()

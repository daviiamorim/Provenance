"""Artifact repository."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from core.model import Artifact
from db.connection import Conn
from db.repos._serialize import provenance_to_dict


def upsert(conn: Conn, a: Artifact) -> None:
    conn.execute(
        """
        INSERT INTO artifacts
            (id, dataset_id, capability_id, kind, payload, depicts, provenance)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (
            a.id,
            a.dataset_id,
            a.capability_id,
            a.kind.value,
            Jsonb(dict(a.payload)),
            list(a.depicts),
            Jsonb(provenance_to_dict(a.provenance)),
        ),
    )


def get(conn: Conn, artifact_id: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM artifacts WHERE id = %s", (artifact_id,))
    return cur.fetchone()


def list_by_dataset(conn: Conn, dataset_id: str) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT * FROM artifacts WHERE dataset_id = %s",
        (dataset_id,),
    )
    return cur.fetchall()

"""Measurement repository."""

from __future__ import annotations

from psycopg.types.json import Jsonb

from core.model import Measurement
from db.connection import Conn
from db.repos._serialize import provenance_to_dict, row_to_measurement, scope_to_cols


def upsert(conn: Conn, m: Measurement) -> None:
    scope_kind, scope_refs = scope_to_cols(m.scope)
    conn.execute(
        """
        INSERT INTO measurements
            (id, dataset_id, type, scope_kind, scope_refs, payload, provenance)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (
            m.id,
            m.dataset_id,
            m.type,
            scope_kind,
            Jsonb(scope_refs),
            Jsonb(dict(m.payload)),
            Jsonb(provenance_to_dict(m.provenance)),
        ),
    )


def get(conn: Conn, measurement_id: str) -> Measurement | None:
    cur = conn.execute(
        "SELECT * FROM measurements WHERE id = %s",
        (measurement_id,),
    )
    row = cur.fetchone()
    return None if row is None else row_to_measurement(row)


def list_by_run(conn: Conn, run_id: str) -> list[Measurement]:
    cur = conn.execute(
        """
        SELECT m.*
        FROM measurements m
        JOIN run_membership_measurements rm ON rm.measurement_id = m.id
        WHERE rm.run_id = %s
        """,
        (run_id,),
    )
    return [row_to_measurement(r) for r in cur.fetchall()]


def get_many(conn: Conn, ids: list[str]) -> list[Measurement]:
    if not ids:
        return []
    cur = conn.execute(
        "SELECT * FROM measurements WHERE id = ANY(%s)",
        (ids,),
    )
    return [row_to_measurement(r) for r in cur.fetchall()]

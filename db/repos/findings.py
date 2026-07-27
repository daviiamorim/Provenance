"""Finding repository."""

from __future__ import annotations

from psycopg.types.json import Jsonb

from core.model import Finding
from db.connection import Conn
from db.repos._serialize import row_to_finding, scope_to_cols


def upsert(conn: Conn, f: Finding) -> None:
    scope_kind, scope_refs = scope_to_cols(f.scope)
    conn.execute(
        """
        INSERT INTO findings
            (id, dataset_id, type, scope_kind, scope_refs, statement,
             severity, derived_from, rule, rule_version, params)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (
            f.id,
            f.dataset_id,
            f.type,
            scope_kind,
            Jsonb(scope_refs),
            f.statement,
            f.severity.value,
            list(f.derived_from),
            f.rule,
            f.rule_version,
            Jsonb(dict(f.params)),
        ),
    )


def get(conn: Conn, finding_id: str) -> Finding | None:
    cur = conn.execute("SELECT * FROM findings WHERE id = %s", (finding_id,))
    row = cur.fetchone()
    return None if row is None else row_to_finding(row)


def list_by_run(conn: Conn, run_id: str) -> list[Finding]:
    cur = conn.execute(
        """
        SELECT f.*
        FROM findings f
        JOIN run_membership_findings rm ON rm.finding_id = f.id
        WHERE rm.run_id = %s
        """,
        (run_id,),
    )
    return [row_to_finding(r) for r in cur.fetchall()]


def get_many(conn: Conn, ids: list[str]) -> list[Finding]:
    if not ids:
        return []
    cur = conn.execute(
        "SELECT * FROM findings WHERE id = ANY(%s)",
        (ids,),
    )
    return [row_to_finding(r) for r in cur.fetchall()]

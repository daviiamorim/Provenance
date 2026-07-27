"""Assessment repository. Assessment.scope is not persisted (see DECISIONS.md)."""

from __future__ import annotations

from psycopg.types.json import Jsonb

from core.model import Assessment
from db.connection import Conn
from db.repos._serialize import row_to_assessment


def upsert(conn: Conn, a: Assessment) -> None:
    conn.execute(
        """
        INSERT INTO assessments
            (id, dataset_id, type, goal, verdict, severity,
             derived_from, rule, rule_version, policy)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (
            a.id,
            a.dataset_id,
            a.type,
            a.goal,
            a.verdict,
            a.severity.value,
            list(a.derived_from),
            a.rule,
            a.rule_version,
            Jsonb(dict(a.policy)),
        ),
    )


def get(conn: Conn, assessment_id: str) -> Assessment | None:
    cur = conn.execute("SELECT * FROM assessments WHERE id = %s", (assessment_id,))
    row = cur.fetchone()
    return None if row is None else row_to_assessment(row)


def list_by_run(conn: Conn, run_id: str) -> list[Assessment]:
    cur = conn.execute(
        """
        SELECT a.*
        FROM assessments a
        JOIN run_membership_assessments rm ON rm.assessment_id = a.id
        WHERE rm.run_id = %s
        """,
        (run_id,),
    )
    return [row_to_assessment(r) for r in cur.fetchall()]


def get_many(conn: Conn, ids: list[str]) -> list[Assessment]:
    if not ids:
        return []
    cur = conn.execute(
        "SELECT * FROM assessments WHERE id = ANY(%s)",
        (ids,),
    )
    return [row_to_assessment(r) for r in cur.fetchall()]

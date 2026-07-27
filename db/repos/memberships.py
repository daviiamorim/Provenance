"""Run membership repositories — three tables with real FK constraints."""

from __future__ import annotations

from db.connection import Conn


def upsert_measurement(conn: Conn, run_id: str, measurement_id: str) -> None:
    conn.execute(
        """
        INSERT INTO run_membership_measurements (run_id, measurement_id)
        VALUES (%s, %s)
        ON CONFLICT (run_id, measurement_id) DO NOTHING
        """,
        (run_id, measurement_id),
    )


def upsert_finding(conn: Conn, run_id: str, finding_id: str) -> None:
    conn.execute(
        """
        INSERT INTO run_membership_findings (run_id, finding_id)
        VALUES (%s, %s)
        ON CONFLICT (run_id, finding_id) DO NOTHING
        """,
        (run_id, finding_id),
    )


def upsert_assessment(conn: Conn, run_id: str, assessment_id: str) -> None:
    conn.execute(
        """
        INSERT INTO run_membership_assessments (run_id, assessment_id)
        VALUES (%s, %s)
        ON CONFLICT (run_id, assessment_id) DO NOTHING
        """,
        (run_id, assessment_id),
    )

"""Claim repository.

The API must never expose claims with status=rejected_discarded to end users;
that filter is enforced here in list_passed_by_run().
"""

from __future__ import annotations

from psycopg.types.json import Jsonb

from core.model import Claim, ValidationStatus
from db.connection import Conn
from db.repos._serialize import row_to_claim, validation_to_dict


def upsert(conn: Conn, c: Claim) -> None:
    conn.execute(
        """
        INSERT INTO claims (id, dataset_id, run_id, text, supports, validation)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (
            c.id,
            c.dataset_id,
            c.run_id,
            c.text,
            list(c.supports),
            Jsonb(validation_to_dict(c.validation)),
        ),
    )


def get(conn: Conn, claim_id: str) -> Claim | None:
    cur = conn.execute("SELECT * FROM claims WHERE id = %s", (claim_id,))
    row = cur.fetchone()
    return None if row is None else row_to_claim(row)


def list_passed_by_run(conn: Conn, run_id: str) -> list[Claim]:
    """Return only passed claims — never expose rejected_discarded to callers."""
    cur = conn.execute(
        """
        SELECT * FROM claims
        WHERE run_id = %s
          AND validation->>'status' = %s
        """,
        (run_id, ValidationStatus.PASSED.value),
    )
    return [row_to_claim(r) for r in cur.fetchall()]


def list_all_by_run(conn: Conn, run_id: str) -> list[Claim]:
    """Return all claims including rejected — for validation/metrics endpoints."""
    cur = conn.execute(
        "SELECT * FROM claims WHERE run_id = %s",
        (run_id,),
    )
    return [row_to_claim(r) for r in cur.fetchall()]

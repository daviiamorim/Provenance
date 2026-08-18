"""Claim rejection repository.

Each RejectionRecord produced by the Composer is persisted here. These records
are product-visible (validation panel), not internal logs.

ID derivation: "rej-" + sha256(run_id | text | attempt)[:24] — deterministic
so re-running the same pipeline is idempotent (ON CONFLICT DO NOTHING).
"""

from __future__ import annotations

import hashlib
from typing import Any

from psycopg.types.json import Jsonb

from core.validation._validator import RejectionRecord
from db.connection import Conn


def _make_id(run_id: str, text: str, attempt: int) -> str:
    raw = f"{run_id}|{text}|{attempt}"
    return "rej-" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def upsert(conn: Conn, run_id: str, r: RejectionRecord) -> None:
    rej_id = _make_id(run_id, r.text, r.attempt)
    conn.execute(
        """
        INSERT INTO claim_rejections
            (id, run_id, text, layer, reason_code, detail, attempt)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (
            rej_id,
            run_id,
            r.text,
            r.layer.value,
            r.reason_code,
            Jsonb(dict(r.detail)),
            r.attempt,
        ),
    )


def list_by_run(conn: Conn, run_id: str) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT * FROM claim_rejections WHERE run_id = %s ORDER BY created_at",
        (run_id,),
    )
    return list(cur.fetchall())

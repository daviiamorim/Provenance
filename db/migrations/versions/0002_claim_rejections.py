"""Add claim_rejections table for persisting validation rejections.

Each row is one rejection event (sentence + layer + reason). A single sentence
can produce up to MAX_ATTEMPTS rows (one per retry). These records are product-
visible — they power the validation panel in the frontend.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
CREATE TABLE claim_rejections (
    id          TEXT        PRIMARY KEY,
    run_id      TEXT        NOT NULL REFERENCES runs(id),
    text        TEXT        NOT NULL,
    layer       TEXT        NOT NULL,
    reason_code TEXT        NOT NULL,
    detail      JSONB       NOT NULL,
    attempt     INT         NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_claim_rejections_run_id ON claim_rejections(run_id);
"""

_DOWN = """
DROP INDEX IF EXISTS idx_claim_rejections_run_id;
DROP TABLE IF EXISTS claim_rejections;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)

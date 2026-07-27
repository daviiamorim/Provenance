"""Initial schema: all four evidence-chain layers + run_membership tables.

Revision ID: 0001
Revises:
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
CREATE TABLE datasets (
    id          TEXT        PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    manifest    JSONB       NOT NULL,
    upload_dir  TEXT        NOT NULL
);

CREATE TABLE runs (
    id                TEXT        PRIMARY KEY,
    dataset_id        TEXT        NOT NULL REFERENCES datasets(id),
    producer_versions JSONB       NOT NULL,
    config_digest     TEXT        NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE measurements (
    id          TEXT  PRIMARY KEY,
    dataset_id  TEXT  NOT NULL REFERENCES datasets(id),
    type        TEXT  NOT NULL,
    scope_kind  TEXT  NOT NULL,
    scope_refs  JSONB NOT NULL,
    payload     JSONB NOT NULL,
    provenance  JSONB NOT NULL
);

CREATE TABLE findings (
    id           TEXT   PRIMARY KEY,
    dataset_id   TEXT   NOT NULL REFERENCES datasets(id),
    type         TEXT   NOT NULL,
    scope_kind   TEXT   NOT NULL,
    scope_refs   JSONB  NOT NULL,
    statement    TEXT   NOT NULL,
    severity     TEXT   NOT NULL,
    derived_from TEXT[] NOT NULL,
    rule         TEXT   NOT NULL,
    rule_version TEXT   NOT NULL,
    params       JSONB  NOT NULL
);

-- Assessment.scope is intentionally NOT persisted; see docs/DECISIONS.md.
CREATE TABLE assessments (
    id           TEXT   PRIMARY KEY,
    dataset_id   TEXT   NOT NULL REFERENCES datasets(id),
    type         TEXT   NOT NULL,
    goal         TEXT   NOT NULL,
    verdict      TEXT   NOT NULL,
    severity     TEXT   NOT NULL,
    derived_from TEXT[] NOT NULL,
    rule         TEXT   NOT NULL,
    rule_version TEXT   NOT NULL,
    policy       JSONB  NOT NULL
);

CREATE TABLE claims (
    id          TEXT   PRIMARY KEY,
    dataset_id  TEXT   NOT NULL REFERENCES datasets(id),
    run_id      TEXT   NOT NULL REFERENCES runs(id),
    text        TEXT   NOT NULL,
    supports    TEXT[] NOT NULL,
    validation  JSONB  NOT NULL
);

CREATE TABLE artifacts (
    id             TEXT   PRIMARY KEY,
    dataset_id     TEXT   NOT NULL REFERENCES datasets(id),
    capability_id  TEXT   NOT NULL,
    kind           TEXT   NOT NULL,
    payload        JSONB  NOT NULL,
    depicts        TEXT[] NOT NULL,
    provenance     JSONB  NOT NULL
);

-- Three separate run_membership tables enforce real FK constraints.
-- A single table with a generic item_id column cannot reference three
-- different parent tables simultaneously; see docs/DECISIONS.md.
CREATE TABLE run_membership_measurements (
    run_id         TEXT NOT NULL REFERENCES runs(id),
    measurement_id TEXT NOT NULL REFERENCES measurements(id),
    PRIMARY KEY (run_id, measurement_id)
);

CREATE TABLE run_membership_findings (
    run_id     TEXT NOT NULL REFERENCES runs(id),
    finding_id TEXT NOT NULL REFERENCES findings(id),
    PRIMARY KEY (run_id, finding_id)
);

CREATE TABLE run_membership_assessments (
    run_id        TEXT NOT NULL REFERENCES runs(id),
    assessment_id TEXT NOT NULL REFERENCES assessments(id),
    PRIMARY KEY (run_id, assessment_id)
);

CREATE INDEX idx_runs_dataset_id ON runs(dataset_id);
CREATE INDEX idx_measurements_dataset_id ON measurements(dataset_id);
CREATE INDEX idx_findings_dataset_id ON findings(dataset_id);
CREATE INDEX idx_assessments_dataset_id ON assessments(dataset_id);
CREATE INDEX idx_claims_run_id ON claims(run_id);
"""

_DOWN = """
DROP TABLE IF EXISTS run_membership_assessments;
DROP TABLE IF EXISTS run_membership_findings;
DROP TABLE IF EXISTS run_membership_measurements;
DROP TABLE IF EXISTS artifacts;
DROP TABLE IF EXISTS claims;
DROP TABLE IF EXISTS assessments;
DROP TABLE IF EXISTS findings;
DROP TABLE IF EXISTS measurements;
DROP TABLE IF EXISTS runs;
DROP TABLE IF EXISTS datasets;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)

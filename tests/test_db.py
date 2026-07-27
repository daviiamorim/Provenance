"""Database repository tests — require TEST_DATABASE_URL (skipped otherwise).

Each test wraps all changes in a transaction that is rolled back at teardown,
so tests are fully isolated from each other without truncating tables.
"""

from __future__ import annotations

from typing import Any

import psycopg

from core.model import (
    Assessment,
    Claim,
    Finding,
    Measurement,
    Provenance,
    Scope,
    ScopeKind,
    Severity,
    ValidationRecord,
    ValidationStatus,
)
from db.repos import assessments as assessment_repo
from db.repos import claims as claim_repo
from db.repos import datasets as dataset_repo
from db.repos import findings as finding_repo
from db.repos import measurements as measurement_repo
from db.repos import memberships
from db.repos import runs as run_repo

# ── fixtures ──────────────────────────────────────────────────────────────────

_DATASET_ID = "dset-" + "a" * 32
_RUN_ID = "run-" + "b" * 32


def _provenance() -> Provenance:
    return Provenance(
        producer="test.producer",
        version="0.0.1",
        params={"k": 1},
        input_digest="d" * 64,
        duration_ms=10,
        seed=None,
    )


def _measurement(*, col: str = "age") -> Measurement:
    return Measurement(
        id=f"msr-{'x' * 32}",
        dataset_id=_DATASET_ID,
        type="core.quality.missing",
        scope=Scope(kind=ScopeKind.COLUMN, refs=(col,)),
        payload={"missing_count": 0, "total_count": 10, "missing_proportion": 0.0},
        provenance=_provenance(),
    )


def _finding(msr_id: str) -> Finding:
    return Finding.create(
        dataset_id=_DATASET_ID,
        type="core.finding.missing_rate",
        scope=Scope(kind=ScopeKind.COLUMN, refs=("age",)),
        statement="Missing rate for 'age' is 0.0% — OK.",
        severity=Severity.OK,
        derived_from=(msr_id,),
        rule="core.finding.missing_rate",
        rule_version="1.0.0",
        params={"warn_threshold": 0.05, "missing_proportion": 0.0},
    )


def _assessment(fnd_id: str) -> Assessment:
    return Assessment.create(
        dataset_id=_DATASET_ID,
        type="core.assessment.data_quality",
        scope=Scope(kind=ScopeKind.DATASET, refs=(_DATASET_ID,)),
        goal="data_quality",
        verdict="acceptable",
        severity=Severity.OK,
        derived_from=(fnd_id,),
        rule="core.assessment.data_quality",
        rule_version="1.0.0",
        policy={"missing_fail_threshold": 0.2},
    )


def _validation_record() -> ValidationRecord:
    return ValidationRecord(
        status=ValidationStatus.PASSED,
        attempts=1,
        checks=(),
        final_layer_reached="semantic",
    )


def _seed_dataset(conn: psycopg.Connection[dict[str, Any]]) -> None:
    dataset_repo.upsert(
        conn,
        _DATASET_ID,
        [{"path": "test.csv", "digest": "a" * 64}],
        "/tmp/test",  # noqa: S108
    )


def _seed_run(conn: psycopg.Connection[dict[str, Any]]) -> None:
    run_repo.upsert(conn, _RUN_ID, _DATASET_ID, {"tabular": "0.1.0"}, "c" * 64)


# ── tests ─────────────────────────────────────────────────────────────────────


def test_dataset_upsert_and_get(
    db_conn: psycopg.Connection[dict[str, Any]],
) -> None:
    dataset_repo.upsert(
        db_conn,
        _DATASET_ID,
        [{"path": "data.csv", "digest": "f" * 64}],
        "/tmp/uploads/test",  # noqa: S108
    )
    row = dataset_repo.get(db_conn, _DATASET_ID)
    assert row is not None
    assert row["id"] == _DATASET_ID
    assert row["manifest"][0]["path"] == "data.csv"
    assert row["upload_dir"] == "/tmp/uploads/test"  # noqa: S108


def test_dataset_upsert_idempotent(
    db_conn: psycopg.Connection[dict[str, Any]],
) -> None:
    dataset_repo.upsert(db_conn, _DATASET_ID, [], "/tmp/a")  # noqa: S108
    dataset_repo.upsert(db_conn, _DATASET_ID, [], "/tmp/b")  # noqa: S108  # second upsert is a no-op
    rows = dataset_repo.list_all(db_conn)
    assert sum(1 for r in rows if r["id"] == _DATASET_ID) == 1


def test_measurement_upsert_and_get(
    db_conn: psycopg.Connection[dict[str, Any]],
) -> None:
    _seed_dataset(db_conn)
    m = _measurement()
    measurement_repo.upsert(db_conn, m)
    fetched = measurement_repo.get(db_conn, m.id)
    assert fetched is not None
    assert fetched.id == m.id
    assert fetched.type == m.type
    assert fetched.scope.kind == ScopeKind.COLUMN
    assert fetched.scope.refs == ("age",)


def test_measurement_idempotent(
    db_conn: psycopg.Connection[dict[str, Any]],
) -> None:
    _seed_dataset(db_conn)
    m = _measurement()
    measurement_repo.upsert(db_conn, m)
    measurement_repo.upsert(db_conn, m)  # ON CONFLICT DO NOTHING
    # No exception means success; the row count is still 1.


def test_finding_upsert_and_get(
    db_conn: psycopg.Connection[dict[str, Any]],
) -> None:
    _seed_dataset(db_conn)
    m = _measurement()
    measurement_repo.upsert(db_conn, m)
    f = _finding(m.id)
    finding_repo.upsert(db_conn, f)
    fetched = finding_repo.get(db_conn, f.id)
    assert fetched is not None
    assert fetched.id == f.id
    assert fetched.severity == Severity.OK
    assert m.id in fetched.derived_from


def test_assessment_upsert_and_get(
    db_conn: psycopg.Connection[dict[str, Any]],
) -> None:
    _seed_dataset(db_conn)
    m = _measurement()
    measurement_repo.upsert(db_conn, m)
    f = _finding(m.id)
    finding_repo.upsert(db_conn, f)
    a = _assessment(f.id)
    assessment_repo.upsert(db_conn, a)
    fetched = assessment_repo.get(db_conn, a.id)
    assert fetched is not None
    assert fetched.goal == "data_quality"
    assert fetched.verdict == "acceptable"


def test_claim_upsert_passed_and_rejected(
    db_conn: psycopg.Connection[dict[str, Any]],
) -> None:
    _seed_dataset(db_conn)
    m = _measurement()
    measurement_repo.upsert(db_conn, m)
    f = _finding(m.id)
    finding_repo.upsert(db_conn, f)
    _seed_run(db_conn)

    passed_claim = Claim.create(
        dataset_id=_DATASET_ID,
        run_id=_RUN_ID,
        text=f"Passed claim [{f.id}].",
        supports=(f.id,),
        validation=ValidationRecord(
            status=ValidationStatus.PASSED,
            attempts=1,
            checks=(),
            final_layer_reached="semantic",
        ),
    )
    rejected_claim = Claim.create(
        dataset_id=_DATASET_ID,
        run_id=_RUN_ID,
        text=f"Rejected claim with bad data [{f.id}].",
        supports=(f.id,),
        validation=ValidationRecord(
            status=ValidationStatus.REJECTED_DISCARDED,
            attempts=2,
            checks=(),
            final_layer_reached="numeric",
        ),
    )
    claim_repo.upsert(db_conn, passed_claim)
    claim_repo.upsert(db_conn, rejected_claim)

    passed_only = claim_repo.list_passed_by_run(db_conn, _RUN_ID)
    assert len(passed_only) == 1
    assert passed_only[0].id == passed_claim.id

    all_claims = claim_repo.list_all_by_run(db_conn, _RUN_ID)
    assert len(all_claims) == 2


def test_run_membership(
    db_conn: psycopg.Connection[dict[str, Any]],
) -> None:
    _seed_dataset(db_conn)
    _seed_run(db_conn)
    m = _measurement()
    measurement_repo.upsert(db_conn, m)
    memberships.upsert_measurement(db_conn, _RUN_ID, m.id)
    memberships.upsert_measurement(db_conn, _RUN_ID, m.id)  # idempotent

    by_run = measurement_repo.list_by_run(db_conn, _RUN_ID)
    assert any(x.id == m.id for x in by_run)


def test_finding_membership(
    db_conn: psycopg.Connection[dict[str, Any]],
) -> None:
    _seed_dataset(db_conn)
    _seed_run(db_conn)
    m = _measurement()
    measurement_repo.upsert(db_conn, m)
    f = _finding(m.id)
    finding_repo.upsert(db_conn, f)
    memberships.upsert_finding(db_conn, _RUN_ID, f.id)

    by_run = finding_repo.list_by_run(db_conn, _RUN_ID)
    assert any(x.id == f.id for x in by_run)


def test_assessment_membership(
    db_conn: psycopg.Connection[dict[str, Any]],
) -> None:
    _seed_dataset(db_conn)
    _seed_run(db_conn)
    m = _measurement()
    measurement_repo.upsert(db_conn, m)
    f = _finding(m.id)
    finding_repo.upsert(db_conn, f)
    a = _assessment(f.id)
    assessment_repo.upsert(db_conn, a)
    memberships.upsert_assessment(db_conn, _RUN_ID, a.id)

    by_run = assessment_repo.list_by_run(db_conn, _RUN_ID)
    assert any(x.id == a.id for x in by_run)

"""Run endpoints: create, query measurements/findings/assessments/claims/metrics."""

from __future__ import annotations

from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_db
from api.schemas import (
    AssessmentOut,
    ClaimOut,
    FindingOut,
    MeasurementOut,
    RunCreateOut,
    RunCreateRequest,
    RunMetrics,
    RunOut,
)
from core.model import ValidationLayer
from db import pipeline as pl
from db.repos import assessments as assessment_repo
from db.repos import claims as claim_repo
from db.repos import findings as finding_repo
from db.repos import measurements as measurement_repo
from db.repos import runs as run_repo

router = APIRouter(prefix="/runs", tags=["runs"])

Conn = psycopg.Connection[dict[str, Any]]


@router.post("", response_model=RunCreateOut, status_code=201)
def create_run(
    body: RunCreateRequest,
    conn: Annotated[Conn, Depends(get_db)],
) -> RunCreateOut:
    """Confirm domain plugin and execute the analysis pipeline.

    The pipeline runs synchronously and persists all results before returning.
    The run is idempotent: re-submitting the same dataset + plugin + goals
    returns the same run_id without re-computing.
    """
    try:
        run_id = pl.run_pipeline(
            conn,
            dataset_id=body.dataset_id,
            plugin_name=body.plugin_name,
            goals=tuple(body.goals),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RunCreateOut(run_id=run_id)


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: str, conn: Annotated[Conn, Depends(get_db)]) -> RunOut:
    row = run_repo.get(conn, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunOut(
        id=str(row["id"]),
        dataset_id=str(row["dataset_id"]),
        producer_versions=dict(row["producer_versions"]),
        config_digest=str(row["config_digest"]),
        created_at=row["created_at"],
    )


@router.get("/{run_id}/measurements", response_model=list[MeasurementOut])
def get_measurements(
    run_id: str,
    conn: Annotated[Conn, Depends(get_db)],
) -> list[MeasurementOut]:
    _require_run(conn, run_id)
    return [
        MeasurementOut.from_model(m) for m in measurement_repo.list_by_run(conn, run_id)
    ]


@router.get("/{run_id}/findings", response_model=list[FindingOut])
def get_findings(
    run_id: str,
    conn: Annotated[Conn, Depends(get_db)],
) -> list[FindingOut]:
    _require_run(conn, run_id)
    return [FindingOut.from_model(f) for f in finding_repo.list_by_run(conn, run_id)]


@router.get("/{run_id}/assessments", response_model=list[AssessmentOut])
def get_assessments(
    run_id: str,
    conn: Annotated[Conn, Depends(get_db)],
) -> list[AssessmentOut]:
    _require_run(conn, run_id)
    return [
        AssessmentOut.from_model(a) for a in assessment_repo.list_by_run(conn, run_id)
    ]


@router.get("/{run_id}/claims", response_model=list[ClaimOut])
def get_claims(
    run_id: str,
    conn: Annotated[Conn, Depends(get_db)],
) -> list[ClaimOut]:
    """Return only passed claims — rejected_discarded are never exposed here."""
    _require_run(conn, run_id)
    return [ClaimOut.from_model(c) for c in claim_repo.list_passed_by_run(conn, run_id)]


@router.get("/{run_id}/validation", response_model=list[ClaimOut])
def get_validation_records(
    run_id: str,
    conn: Annotated[Conn, Depends(get_db)],
) -> list[ClaimOut]:
    """Return all claims including rejected ones — for the validation audit panel."""
    _require_run(conn, run_id)
    return [ClaimOut.from_model(c) for c in claim_repo.list_all_by_run(conn, run_id)]


@router.get("/{run_id}/metrics", response_model=RunMetrics)
def get_metrics(
    run_id: str,
    conn: Annotated[Conn, Depends(get_db)],
) -> RunMetrics:
    """Rejection metrics for this run, computed from all stored claims."""
    _require_run(conn, run_id)
    all_claims = claim_repo.list_all_by_run(conn, run_id)

    total = len(all_claims)
    passed = sum(1 for c in all_claims if c.validation.status.value == "passed")
    discarded = total - passed

    def _reject_rate(layer: ValidationLayer) -> float:
        rejected = sum(
            1
            for c in all_claims
            if any(
                ch.layer == layer and ch.verdict.value == "fail"
                for ch in c.validation.checks
            )
        )
        return rejected / total if total else 0.0

    return RunMetrics(
        run_id=run_id,
        total_claims=total,
        total_passed=passed,
        total_discarded=discarded,
        rejection_rate_syntactic=_reject_rate(ValidationLayer.SYNTACTIC),
        rejection_rate_numeric=_reject_rate(ValidationLayer.NUMERIC),
        rejection_rate_semantic=_reject_rate(ValidationLayer.SEMANTIC),
    )


def _require_run(conn: Conn, run_id: str) -> None:
    if run_repo.get(conn, run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")

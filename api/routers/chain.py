"""Evidence chain endpoint — navigate Claim → Assessment → Finding → Measurement."""

from __future__ import annotations

from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_db
from api.schemas import (
    AssessmentOut,
    ClaimOut,
    EvidenceChain,
    FindingOut,
    MeasurementOut,
)
from db.repos import assessments as assessment_repo
from db.repos import claims as claim_repo
from db.repos import findings as finding_repo
from db.repos import measurements as measurement_repo

router = APIRouter(prefix="/chain", tags=["chain"])

Conn = psycopg.Connection[dict[str, Any]]


@router.get("/{item_id}", response_model=EvidenceChain)
def get_chain(
    item_id: str,
    conn: Annotated[Conn, Depends(get_db)],
) -> EvidenceChain:
    """Return the full evidence chain rooted at item_id.

    Given any id (clm-, ast-, fnd-, or msr-), traverses the chain downward
    collecting all reachable evidence items.
    """
    if item_id.startswith("clm-"):
        return _chain_from_claim(conn, item_id)
    if item_id.startswith("ast-"):
        return _chain_from_assessment(conn, item_id)
    if item_id.startswith("fnd-"):
        return _chain_from_finding(conn, item_id)
    if item_id.startswith("msr-"):
        return _chain_from_measurement(conn, item_id)
    raise HTTPException(
        status_code=422,
        detail=(
            f"Unknown item prefix for {item_id!r}. Expected clm-, ast-, fnd-, or msr-."
        ),
    )


def _chain_from_claim(conn: Conn, claim_id: str) -> EvidenceChain:
    claim = claim_repo.get(conn, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    support_ids = list(claim.supports)
    fnd_ids = [s for s in support_ids if s.startswith("fnd-")]
    ast_ids = [s for s in support_ids if s.startswith("ast-")]

    found_assessments = assessment_repo.get_many(conn, ast_ids)
    found_findings = finding_repo.get_many(conn, fnd_ids)

    # Collect findings referenced by assessments
    for a in found_assessments:
        extra_fnd_ids = [f for f in a.derived_from if f not in fnd_ids]
        found_findings.extend(finding_repo.get_many(conn, extra_fnd_ids))
        fnd_ids.extend(extra_fnd_ids)

    # Collect measurements referenced by findings
    all_msr_ids: list[str] = []
    for f in found_findings:
        all_msr_ids.extend(m for m in f.derived_from if m not in all_msr_ids)

    found_measurements = measurement_repo.get_many(conn, all_msr_ids)

    return EvidenceChain(
        root_id=claim_id,
        claim=ClaimOut.from_model(claim),
        assessments=[AssessmentOut.from_model(a) for a in found_assessments],
        findings=[FindingOut.from_model(f) for f in found_findings],
        measurements=[MeasurementOut.from_model(m) for m in found_measurements],
    )


def _chain_from_assessment(conn: Conn, assessment_id: str) -> EvidenceChain:
    a = assessment_repo.get(conn, assessment_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    found_findings = finding_repo.get_many(conn, list(a.derived_from))
    all_msr_ids: list[str] = []
    for f in found_findings:
        all_msr_ids.extend(m for m in f.derived_from if m not in all_msr_ids)

    return EvidenceChain(
        root_id=assessment_id,
        assessments=[AssessmentOut.from_model(a)],
        findings=[FindingOut.from_model(f) for f in found_findings],
        measurements=[
            MeasurementOut.from_model(m)
            for m in measurement_repo.get_many(conn, all_msr_ids)
        ],
    )


def _chain_from_finding(conn: Conn, finding_id: str) -> EvidenceChain:
    f = finding_repo.get(conn, finding_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    return EvidenceChain(
        root_id=finding_id,
        findings=[FindingOut.from_model(f)],
        measurements=[
            MeasurementOut.from_model(m)
            for m in measurement_repo.get_many(conn, list(f.derived_from))
        ],
    )


def _chain_from_measurement(conn: Conn, measurement_id: str) -> EvidenceChain:
    m = measurement_repo.get(conn, measurement_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Measurement not found")
    return EvidenceChain(
        root_id=measurement_id,
        measurements=[MeasurementOut.from_model(m)],
    )

"""Pydantic response models for the data-observatory API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ScopeOut(BaseModel):
    kind: str
    refs: list[str]


class ProvenanceOut(BaseModel):
    producer: str
    version: str
    params: dict[str, Any]
    input_digest: str
    duration_ms: int
    seed: int | None


class MeasurementOut(BaseModel):
    id: str
    dataset_id: str
    type: str
    scope: ScopeOut
    payload: dict[str, Any]
    provenance: ProvenanceOut

    @classmethod
    def from_model(cls, m: Any) -> MeasurementOut:
        return cls(
            id=m.id,
            dataset_id=m.dataset_id,
            type=m.type,
            scope=ScopeOut(kind=m.scope.kind.value, refs=list(m.scope.refs)),
            payload=dict(m.payload),
            provenance=ProvenanceOut(
                producer=m.provenance.producer,
                version=m.provenance.version,
                params=dict(m.provenance.params),
                input_digest=m.provenance.input_digest,
                duration_ms=m.provenance.duration_ms,
                seed=m.provenance.seed,
            ),
        )


class FindingOut(BaseModel):
    id: str
    dataset_id: str
    type: str
    scope: ScopeOut
    statement: str
    severity: str
    derived_from: list[str]
    rule: str
    rule_version: str
    params: dict[str, Any]

    @classmethod
    def from_model(cls, f: Any) -> FindingOut:
        return cls(
            id=f.id,
            dataset_id=f.dataset_id,
            type=f.type,
            scope=ScopeOut(kind=f.scope.kind.value, refs=list(f.scope.refs)),
            statement=f.statement,
            severity=f.severity.value,
            derived_from=list(f.derived_from),
            rule=f.rule,
            rule_version=f.rule_version,
            params=dict(f.params),
        )


class AssessmentOut(BaseModel):
    id: str
    dataset_id: str
    type: str
    goal: str
    verdict: str
    severity: str
    derived_from: list[str]
    rule: str
    rule_version: str
    policy: dict[str, Any]
    # scope is intentionally absent — not persisted; see docs/DECISIONS.md

    @classmethod
    def from_model(cls, a: Any) -> AssessmentOut:
        return cls(
            id=a.id,
            dataset_id=a.dataset_id,
            type=a.type,
            goal=a.goal,
            verdict=a.verdict,
            severity=a.severity.value,
            derived_from=list(a.derived_from),
            rule=a.rule,
            rule_version=a.rule_version,
            policy=dict(a.policy),
        )


class ValidationCheckOut(BaseModel):
    layer: str
    verdict: str
    reason_code: str
    detail: dict[str, Any]
    duration_ms: int


class ValidationRecordOut(BaseModel):
    status: str
    attempts: int
    checks: list[ValidationCheckOut]
    final_layer_reached: str


class ClaimOut(BaseModel):
    id: str
    dataset_id: str
    run_id: str
    text: str
    explanation: str = ""
    supports: list[str]
    validation: ValidationRecordOut

    @classmethod
    def from_model(cls, c: Any) -> ClaimOut:
        v = c.validation
        return cls(
            id=c.id,
            dataset_id=c.dataset_id,
            run_id=c.run_id,
            text=c.text,
            explanation=getattr(c, "explanation", ""),
            supports=list(c.supports),
            validation=ValidationRecordOut(
                status=v.status.value,
                attempts=v.attempts,
                checks=[
                    ValidationCheckOut(
                        layer=ch.layer.value,
                        verdict=ch.verdict.value,
                        reason_code=ch.reason_code,
                        detail=dict(ch.detail),
                        duration_ms=ch.duration_ms,
                    )
                    for ch in v.checks
                ],
                final_layer_reached=v.final_layer_reached,
            ),
        )


class DatasetOut(BaseModel):
    id: str
    created_at: datetime
    manifest: list[dict[str, str]]


class RunOut(BaseModel):
    id: str
    dataset_id: str
    producer_versions: dict[str, str]
    config_digest: str
    created_at: datetime


class DomainCandidate(BaseModel):
    plugin_name: str
    confidence: float
    evidence: str


class UploadOut(BaseModel):
    dataset_id: str
    candidates: list[DomainCandidate]


class RunCreateRequest(BaseModel):
    dataset_id: str
    plugin_name: str = "tabular"
    goals: list[str] = ["data_quality", "modeling_readiness"]


class RunCreateOut(BaseModel):
    run_id: str


class RejectionOut(BaseModel):
    id: str
    run_id: str
    text: str
    layer: str
    reason_code: str
    detail: dict[str, Any]
    attempt: int


class RunCounts(BaseModel):
    measurements: int
    findings: int
    assessments: int
    claims_passed: int


class SeverityCounts(BaseModel):
    ok: int
    warn: int
    fail: int


class RunMetrics(BaseModel):
    run_id: str
    counts: RunCounts
    severity: SeverityCounts
    total_rejections: int
    rejections_syntactic: int
    rejections_numeric: int
    rejections_semantic: int


class ClaimSummary(BaseModel):
    id: str
    text: str
    explanation: str = ""
    supports: list[str]
    severity: str


class ReportCounts(BaseModel):
    rows: int | None
    columns: int
    findings: int
    claims: int


class ReportSection(BaseModel):
    goal: str
    claims: list[ClaimSummary]


class ReportOut(BaseModel):
    run_id: str
    dataset_id: str
    dataset_name: str
    counts: ReportCounts
    sections: list[ReportSection]


class EvidenceChain(BaseModel):
    root_id: str
    claim: ClaimOut | None = None
    assessments: list[AssessmentOut] = []
    findings: list[FindingOut] = []
    measurements: list[MeasurementOut] = []


class CapabilityOut(BaseModel):
    id: str
    description: str
    params_schema: dict[str, Any]
    produces: list[str]
    renders: bool
    cost: str


class CatalogOut(BaseModel):
    plugin_name: str
    capabilities: list[CapabilityOut]
    measurement_types: list[str]

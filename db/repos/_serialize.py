"""Serialization helpers: domain model objects ↔ DB-row dicts."""

from __future__ import annotations

from typing import Any

from core.model import (
    Assessment,
    Claim,
    Finding,
    Measurement,
    Provenance,
    Scope,
    ScopeKind,
    Severity,
    ValidationCheck,
    ValidationLayer,
    ValidationRecord,
    ValidationStatus,
    ValidationVerdict,
)

# ── Provenance ────────────────────────────────────────────────────────────────


def provenance_to_dict(p: Provenance) -> dict[str, Any]:
    return {
        "producer": p.producer,
        "version": p.version,
        "params": dict(p.params),
        "input_digest": p.input_digest,
        "duration_ms": p.duration_ms,
        "seed": p.seed,
    }


def dict_to_provenance(d: dict[str, Any]) -> Provenance:
    return Provenance(
        producer=str(d["producer"]),
        version=str(d["version"]),
        params=dict(d["params"]),
        input_digest=str(d["input_digest"]),
        duration_ms=int(d["duration_ms"]),
        seed=int(d["seed"]) if d.get("seed") is not None else None,
    )


# ── Scope ─────────────────────────────────────────────────────────────────────


def scope_to_cols(scope: Scope) -> tuple[str, list[str]]:
    return scope.kind.value, list(scope.refs)


def cols_to_scope(kind: str, refs: list[Any]) -> Scope:
    return Scope(kind=ScopeKind(kind), refs=tuple(str(r) for r in refs))


# ── ValidationRecord ──────────────────────────────────────────────────────────


def validation_to_dict(v: ValidationRecord) -> dict[str, Any]:
    return {
        "status": v.status.value,
        "attempts": v.attempts,
        "checks": [
            {
                "layer": c.layer.value,
                "verdict": c.verdict.value,
                "reason_code": c.reason_code,
                "detail": dict(c.detail),
                "duration_ms": c.duration_ms,
            }
            for c in v.checks
        ],
        "final_layer_reached": v.final_layer_reached,
    }


def dict_to_validation(d: dict[str, Any]) -> ValidationRecord:
    checks = tuple(
        ValidationCheck(
            layer=ValidationLayer(str(c["layer"])),
            verdict=ValidationVerdict(str(c["verdict"])),
            reason_code=str(c["reason_code"]),
            detail=dict(c["detail"]),
            duration_ms=int(c["duration_ms"]),
        )
        for c in d.get("checks", [])
    )
    return ValidationRecord(
        status=ValidationStatus(str(d["status"])),
        attempts=int(d["attempts"]),
        checks=checks,
        final_layer_reached=str(d["final_layer_reached"]),
    )


# ── Measurement ───────────────────────────────────────────────────────────────


def row_to_measurement(row: dict[str, Any]) -> Measurement:
    return Measurement(
        id=str(row["id"]),
        dataset_id=str(row["dataset_id"]),
        type=str(row["type"]),
        scope=cols_to_scope(str(row["scope_kind"]), list(row["scope_refs"])),
        payload=dict(row["payload"]),
        provenance=dict_to_provenance(dict(row["provenance"])),
    )


# ── Finding ───────────────────────────────────────────────────────────────────


def row_to_finding(row: dict[str, Any]) -> Finding:
    return Finding(
        id=str(row["id"]),
        dataset_id=str(row["dataset_id"]),
        type=str(row["type"]),
        scope=cols_to_scope(str(row["scope_kind"]), list(row["scope_refs"])),
        statement=str(row["statement"]),
        severity=Severity(str(row["severity"])),
        derived_from=tuple(str(x) for x in row["derived_from"]),
        rule=str(row["rule"]),
        rule_version=str(row["rule_version"]),
        params=dict(row["params"]),
    )


# ── Assessment ────────────────────────────────────────────────────────────────


def row_to_assessment(row: dict[str, Any]) -> Assessment:
    return Assessment(
        id=str(row["id"]),
        dataset_id=str(row["dataset_id"]),
        type=str(row["type"]),
        goal=str(row["goal"]),
        verdict=str(row["verdict"]),
        severity=Severity(str(row["severity"])),
        derived_from=tuple(str(x) for x in row["derived_from"]),
        rule=str(row["rule"]),
        rule_version=str(row["rule_version"]),
        policy=dict(row["policy"]),
    )


# ── Claim ─────────────────────────────────────────────────────────────────────


def row_to_claim(row: dict[str, Any]) -> Claim:
    return Claim(
        id=str(row["id"]),
        dataset_id=str(row["dataset_id"]),
        run_id=str(row["run_id"]),
        text=str(row["text"]),
        explanation=str(row.get("explanation", "")),
        supports=tuple(str(x) for x in row["supports"]),
        validation=dict_to_validation(dict(row["validation"])),
    )

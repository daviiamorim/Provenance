"""Four-layer evidence-chain data model with deterministic provenance."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final

import jsonschema
import jsonschema.validators

__all__ = [
    "MEASUREMENT_SCHEMA_REGISTRY",
    "Artifact",
    "ArtifactKind",
    "Assessment",
    "CapabilityResult",
    "Claim",
    "Finding",
    "Layer",
    "Measurement",
    "Provenance",
    "Scope",
    "ScopeKind",
    "Severity",
    "ValidationCheck",
    "ValidationLayer",
    "ValidationRecord",
    "ValidationStatus",
    "ValidationVerdict",
    "canonical_json",
    "derive_claim_id",
    "derive_dataset_id",
    "derive_run_id",
]

# ── Enumerations ──────────────────────────────────────────────────────────────


class Layer(StrEnum):
    MEASUREMENT = "measurement"
    FINDING = "finding"
    ASSESSMENT = "assessment"
    CLAIM = "claim"


class Severity(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


class ScopeKind(StrEnum):
    DATASET = "dataset"
    FILE = "file"
    COLUMN = "column"
    CHANNEL = "channel"
    SEGMENT = "segment"
    PAIR = "pair"


class ArtifactKind(StrEnum):
    VEGA_LITE = "vega_lite"
    IMAGE = "image"
    AUDIO = "audio"


class ValidationLayer(StrEnum):
    SYNTACTIC = "syntactic"
    NUMERIC = "numeric"
    SEMANTIC = "semantic"


class ValidationVerdict(StrEnum):
    PASS = "pass"  # noqa: S105
    FAIL = "fail"


class ValidationStatus(StrEnum):
    PASSED = "passed"
    REJECTED_DISCARDED = "rejected_discarded"


# ── Canonical serialization ───────────────────────────────────────────────────

_SCHEMA_DIR: Final = Path(__file__).parent.parent / "schemas" / "measurements"


def _normalize_float(value: float) -> int | float:
    """Normalize a float: reject NaN/Inf, -0.0→0.0, integral→int."""
    if math.isnan(value) or math.isinf(value):
        raise ValueError(
            f"NaN and Infinity are forbidden in canonical params: {value!r}"
        )
    normalized = 0.0 if value == -0.0 else value
    return int(normalized) if normalized == int(normalized) else normalized


def _normalize(obj: object) -> object:  # noqa: PLR0911
    """Recursively normalize a value for canonical JSON serialization.

    These rules are load-bearing for ID stability. The anchor test in the
    test suite detects any accidental drift.
    """
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return _normalize_float(obj)
    if isinstance(obj, int):
        return obj
    if isinstance(obj, str):
        return obj
    if obj is None:
        return obj
    if isinstance(obj, (dict, MappingProxyType)):
        return {str(k): _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    raise TypeError(f"Unsupported type in canonical serialization: {type(obj)!r}")


def canonical_json(obj: object) -> bytes:
    """Return canonical UTF-8 JSON bytes of obj, suitable for hashing.

    Rules: sort_keys=True, no spaces, NaN/Infinity forbidden, -0.0→0.0,
    integral floats→int. These rules are frozen — changing them silently
    rotates all IDs. The anchor test in the test suite detects any drift.
    """
    return json.dumps(
        _normalize(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_prefix(data: bytes, prefix: str) -> str:
    return f"{prefix}-{hashlib.sha256(data).hexdigest()[:32]}"


# ── Top-level ID derivation ───────────────────────────────────────────────────


def derive_dataset_id(files: list[tuple[str, str]]) -> str:
    """Derive dataset_id from a manifest of (relative_path, sha256_of_file) pairs.

    Sorted by path, serialized canonically. Same content always → same id.
    """
    manifest = [{"path": p, "digest": d} for p, d in sorted(files, key=lambda x: x[0])]
    return _sha256_prefix(canonical_json(manifest), "dset")


def derive_run_id(
    dataset_id: str,
    producer_versions: Mapping[str, str],
    config_digest: str,
) -> str:
    """Derive run_id from dataset identity, producer versions, and config digest."""
    identity: dict[str, object] = {
        "config_digest": config_digest,
        "dataset_id": dataset_id,
        "producers": dict(sorted(producer_versions.items())),
    }
    return _sha256_prefix(canonical_json(identity), "run")


def derive_claim_id(run_id: str, text: str, supports: tuple[str, ...]) -> str:
    """Derive Claim.id from run, normalized text, and sorted supports."""
    identity: dict[str, object] = {
        "run_id": run_id,
        "supports": sorted(supports),
        "text": unicodedata.normalize("NFC", text.strip()),
    }
    return _sha256_prefix(canonical_json(identity), "clm")


# ── Schema registry ───────────────────────────────────────────────────────────


class SchemaRegistry:
    """Registry of JSON Schemas for Measurement types."""

    def __init__(self) -> None:
        self._schemas: dict[str, dict[str, object]] = {}
        self._validators: dict[str, jsonschema.protocols.Validator] = {}
        self._symmetric: set[str] = set()

    def register(
        self,
        type_name: str,
        schema: dict[str, object],
        *,
        symmetric: bool = False,
    ) -> None:
        cls = jsonschema.validators.validator_for(schema)
        cls.check_schema(schema)
        self._schemas[type_name] = schema
        self._validators[type_name] = cls(schema)
        if symmetric:
            self._symmetric.add(type_name)

    def validate(self, type_name: str, payload: Mapping[str, object]) -> None:
        if type_name not in self._validators:
            raise ValueError(f"Unregistered measurement type: {type_name!r}")
        try:
            self._validators[type_name].validate(dict(payload))
        except jsonschema.ValidationError as exc:
            msg = f"Invalid payload for {type_name!r}: {exc.message}"
            raise ValueError(msg) from exc

    def is_symmetric(self, type_name: str) -> bool:
        return type_name in self._symmetric

    def registered_types(self) -> frozenset[str]:
        return frozenset(self._schemas)


MEASUREMENT_SCHEMA_REGISTRY: Final[SchemaRegistry] = SchemaRegistry()


def _load_builtin_schemas() -> None:
    if not _SCHEMA_DIR.exists():
        return
    for path in sorted(_SCHEMA_DIR.glob("*.json")):
        schema: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        symmetric = bool(schema.get("x-symmetric", False))
        MEASUREMENT_SCHEMA_REGISTRY.register(path.stem, schema, symmetric=symmetric)


_load_builtin_schemas()


# ── Core structures ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Scope:
    kind: ScopeKind
    refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.refs, tuple):
            raise TypeError(f"Scope.refs must be tuple, got {type(self.refs).__name__}")


def _freeze_mapping(m: Mapping[str, object]) -> MappingProxyType[str, object]:
    return MappingProxyType(dict(m))


@dataclass(frozen=True)
class Provenance:
    producer: str
    version: str
    params: Mapping[str, object]
    input_digest: str
    duration_ms: int
    seed: int | None

    def __post_init__(self) -> None:
        _normalize(self.params)  # raises on NaN/Infinity/unsupported types
        object.__setattr__(self, "params", _freeze_mapping(self.params))


# ── Per-layer ID derivation ───────────────────────────────────────────────────


def _scope_dict(scope: Scope, *, sort_refs: bool = False) -> dict[str, object]:
    refs: list[str] = sorted(scope.refs) if sort_refs else list(scope.refs)
    return {"kind": scope.kind.value, "refs": refs}


def _derive_measurement_id(
    dataset_id: str,
    type_: str,
    scope: Scope,
    provenance: Provenance,
) -> str:
    sort_refs = MEASUREMENT_SCHEMA_REGISTRY.is_symmetric(type_)
    identity: dict[str, object] = {
        "dataset_id": dataset_id,
        "params": dict(provenance.params),
        "producer": provenance.producer,
        "scope": _scope_dict(scope, sort_refs=sort_refs),
        "type": type_,
        "version": provenance.version,
    }
    return _sha256_prefix(canonical_json(identity), "msr")


def _derive_finding_id(
    dataset_id: str,
    type_: str,
    scope: Scope,
    rule: str,
    rule_version: str,
    params: Mapping[str, object],
) -> str:
    identity: dict[str, object] = {
        "dataset_id": dataset_id,
        "params": dict(params),
        "producer": rule,
        "scope": _scope_dict(scope),
        "type": type_,
        "version": rule_version,
    }
    return _sha256_prefix(canonical_json(identity), "fnd")


def _derive_assessment_id(
    dataset_id: str,
    type_: str,
    scope: Scope,
    goal: str,
    policy: Mapping[str, object],
    rule: str,
    rule_version: str,
) -> str:
    identity: dict[str, object] = {
        "dataset_id": dataset_id,
        "goal": goal,
        "params": dict(policy),
        "producer": rule,
        "scope": _scope_dict(scope),
        "type": type_,
        "version": rule_version,
    }
    return _sha256_prefix(canonical_json(identity), "ast")


def _derive_artifact_id(
    dataset_id: str,
    capability_id: str,
    provenance: Provenance,
) -> str:
    identity: dict[str, object] = {
        "capability_id": capability_id,
        "dataset_id": dataset_id,
        "params": dict(provenance.params),
        "producer": provenance.producer,
        "version": provenance.version,
    }
    return _sha256_prefix(canonical_json(identity), "art")


# ── Prefix validation ─────────────────────────────────────────────────────────

_VALID_PREFIXES: Final[dict[str, frozenset[str]]] = {
    "Finding.derived_from": frozenset({"msr-"}),
    "Assessment.derived_from": frozenset({"fnd-"}),
    "Claim.supports": frozenset({"fnd-", "ast-"}),
    "Artifact.depicts": frozenset({"msr-"}),
}


def _check_refs(refs: tuple[str, ...], field: str) -> None:
    valid = _VALID_PREFIXES[field]
    for ref in refs:
        if not any(ref.startswith(p) for p in valid):
            allowed = " or ".join(sorted(valid))
            raise ValueError(
                f"{field} requires ids with prefix {allowed}, got {ref!r}"
            )


# ── ValidationCheck / ValidationRecord ───────────────────────────────────────


@dataclass(frozen=True)
class ValidationCheck:
    layer: ValidationLayer
    verdict: ValidationVerdict
    reason_code: str
    detail: Mapping[str, object]
    duration_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "detail", _freeze_mapping(self.detail))


@dataclass(frozen=True)
class ValidationRecord:
    status: ValidationStatus
    attempts: int
    checks: tuple[ValidationCheck, ...]
    final_layer_reached: str


# ── Four-layer data model ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Measurement:
    id: str
    dataset_id: str
    type: str
    scope: Scope
    payload: Mapping[str, object]
    provenance: Provenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze_mapping(self.payload))

    @classmethod
    def create(
        cls,
        *,
        dataset_id: str,
        type: str,  # noqa: A002
        scope: Scope,
        payload: Mapping[str, object],
        provenance: Provenance,
    ) -> Measurement:
        MEASUREMENT_SCHEMA_REGISTRY.validate(type, payload)
        id_ = _derive_measurement_id(dataset_id, type, scope, provenance)
        return cls(
            id=id_,
            dataset_id=dataset_id,
            type=type,
            scope=scope,
            payload=payload,
            provenance=provenance,
        )


@dataclass(frozen=True)
class Finding:
    id: str
    dataset_id: str
    type: str
    scope: Scope
    statement: str
    severity: Severity
    derived_from: tuple[str, ...]
    rule: str
    rule_version: str
    params: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.derived_from:
            raise ValueError("Finding.derived_from cannot be empty")
        _check_refs(self.derived_from, "Finding.derived_from")
        _normalize(self.params)  # raises on NaN/Infinity/unsupported types
        object.__setattr__(self, "params", _freeze_mapping(self.params))

    @classmethod
    def create(
        cls,
        *,
        dataset_id: str,
        type: str,  # noqa: A002
        scope: Scope,
        statement: str,
        severity: Severity,
        derived_from: tuple[str, ...],
        rule: str,
        rule_version: str,
        params: Mapping[str, object],
    ) -> Finding:
        id_ = _derive_finding_id(dataset_id, type, scope, rule, rule_version, params)
        return cls(
            id=id_,
            dataset_id=dataset_id,
            type=type,
            scope=scope,
            statement=statement,
            severity=severity,
            derived_from=derived_from,
            rule=rule,
            rule_version=rule_version,
            params=params,
        )


@dataclass(frozen=True)
class Assessment:
    id: str
    dataset_id: str
    type: str
    goal: str
    verdict: str
    severity: Severity
    derived_from: tuple[str, ...]
    rule: str
    rule_version: str
    policy: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.derived_from:
            raise ValueError("Assessment.derived_from cannot be empty")
        _check_refs(self.derived_from, "Assessment.derived_from")
        object.__setattr__(self, "policy", _freeze_mapping(self.policy))

    @classmethod
    def create(
        cls,
        *,
        dataset_id: str,
        type: str,  # noqa: A002
        scope: Scope,
        goal: str,
        verdict: str,
        severity: Severity,
        derived_from: tuple[str, ...],
        rule: str,
        rule_version: str,
        policy: Mapping[str, object],
    ) -> Assessment:
        id_ = _derive_assessment_id(
            dataset_id, type, scope, goal, policy, rule, rule_version
        )
        return cls(
            id=id_,
            dataset_id=dataset_id,
            type=type,
            goal=goal,
            verdict=verdict,
            severity=severity,
            derived_from=derived_from,
            rule=rule,
            rule_version=rule_version,
            policy=policy,
        )


@dataclass(frozen=True)
class Claim:
    id: str
    dataset_id: str
    run_id: str
    text: str
    supports: tuple[str, ...]
    validation: ValidationRecord

    def __post_init__(self) -> None:
        if not self.supports:
            raise ValueError("Claim.supports cannot be empty")
        _check_refs(self.supports, "Claim.supports")

    @classmethod
    def create(
        cls,
        *,
        dataset_id: str,
        run_id: str,
        text: str,
        supports: tuple[str, ...],
        validation: ValidationRecord,
    ) -> Claim:
        id_ = derive_claim_id(run_id, text, supports)
        return cls(
            id=id_,
            dataset_id=dataset_id,
            run_id=run_id,
            text=text,
            supports=supports,
            validation=validation,
        )


@dataclass(frozen=True)
class Artifact:
    id: str
    dataset_id: str
    capability_id: str
    kind: ArtifactKind
    payload: Mapping[str, object]
    depicts: tuple[str, ...]
    provenance: Provenance

    def __post_init__(self) -> None:
        if not self.depicts:
            raise ValueError("Artifact.depicts cannot be empty")
        _check_refs(self.depicts, "Artifact.depicts")
        object.__setattr__(self, "payload", _freeze_mapping(self.payload))

    @classmethod
    def create(
        cls,
        *,
        dataset_id: str,
        capability_id: str,
        kind: ArtifactKind,
        payload: Mapping[str, object],
        depicts: tuple[str, ...],
        provenance: Provenance,
    ) -> Artifact:
        id_ = _derive_artifact_id(dataset_id, capability_id, provenance)
        return cls(
            id=id_,
            dataset_id=dataset_id,
            capability_id=capability_id,
            kind=kind,
            payload=payload,
            depicts=depicts,
            provenance=provenance,
        )


# ── CapabilityResult ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CapabilityResult:
    measurements: tuple[Measurement, ...]
    artifacts: tuple[Artifact, ...]

    def __post_init__(self) -> None:
        if self.artifacts and not self.measurements:
            raise ValueError(
                "CapabilityResult with artifacts must include at least one measurement"
            )

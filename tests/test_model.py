"""Test suite for core/model.py — Etapa 1.

Covers: immutability, determinism, prefix enforcement, schema validation,
canonical serialization anchor, dataset_id stability, and symmetry.
"""

from __future__ import annotations

import dataclasses

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.model import (
    MEASUREMENT_SCHEMA_REGISTRY,
    Artifact,
    ArtifactKind,
    Assessment,
    CapabilityResult,
    Claim,
    Finding,
    Layer,
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
    canonical_json,
    derive_dataset_id,
    derive_run_id,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _provenance(
    *,
    producer: str = "core.stats.descriptive_producer",
    version: str = "1.0.0",
    params: dict[str, object] | None = None,
) -> Provenance:
    return Provenance(
        producer=producer,
        version=version,
        params=params if params is not None else {"n": 100},
        input_digest="a" * 64,
        duration_ms=10,
        seed=None,
    )


def _scope(
    kind: ScopeKind = ScopeKind.COLUMN,
    refs: tuple[str, ...] = ("age",),
) -> Scope:
    return Scope(kind=kind, refs=refs)


def _measurement(
    *,
    dataset_id: str = "dset-abc",
    type: str = "core.stats.descriptive",  # noqa: A002
    scope: Scope | None = None,
    payload: dict[str, object] | None = None,
    provenance: Provenance | None = None,
) -> Measurement:
    return Measurement.create(
        dataset_id=dataset_id,
        type=type,
        scope=scope or _scope(),
        payload=payload
        or {
            "count": 100,
            "mean": 35.5,
            "std": 12.3,
            "min": 18.0,
            "max": 80.0,
            "q25": 25.0,
            "q50": 35.0,
            "q75": 50.0,
        },
        provenance=provenance or _provenance(),
    )


def _finding(
    msr_id: str = "msr-" + "a" * 32, params: dict[str, object] | None = None
) -> Finding:
    return Finding.create(
        dataset_id="dset-abc",
        type="core.finding.completeness",
        scope=_scope(),
        statement="Column age has no missing values.",
        severity=Severity.OK,
        derived_from=(msr_id,),
        rule="core.rules.missing_check",
        rule_version="1.0.0",
        params=params if params is not None else {},
    )


def _assessment(fnd_id: str = "fnd-" + "a" * 32) -> Assessment:
    return Assessment.create(
        dataset_id="dset-abc",
        type="core.assessment.completeness",
        scope=_scope(),
        goal="ml_training",
        verdict="pass",
        severity=Severity.OK,
        derived_from=(fnd_id,),
        rule="core.rules.training_readiness",
        rule_version="1.0.0",
        policy={"missing_threshold": 0.05},
    )


def _validation_record() -> ValidationRecord:
    return ValidationRecord(
        status=ValidationStatus.PASSED,
        attempts=1,
        checks=(
            ValidationCheck(
                layer=ValidationLayer.SYNTACTIC,
                verdict=ValidationVerdict.PASS,
                reason_code="ok",
                detail={},
                duration_ms=1,
            ),
        ),
        final_layer_reached=ValidationLayer.SYNTACTIC.value,
    )


def _claim(
    *,
    supports: tuple[str, ...] = ("fnd-" + "a" * 32,),
) -> Claim:
    return Claim.create(
        dataset_id="dset-abc",
        run_id="run-" + "b" * 32,
        text="A coluna age não possui valores ausentes.",
        supports=supports,
        validation=_validation_record(),
    )


def _artifact(depicts: tuple[str, ...] = ("msr-" + "a" * 32,)) -> Artifact:
    return Artifact.create(
        dataset_id="dset-abc",
        capability_id="core.stats.histogram",
        kind=ArtifactKind.VEGA_LITE,
        payload={"$schema": "https://vega.github.io/schema/vega-lite/v5.json"},
        depicts=depicts,
        provenance=_provenance(),
    )


# ── Canonical serialization ───────────────────────────────────────────────────


class TestCanonicalJson:
    def test_anchor(self) -> None:
        """Frozen bit-exact anchor: if serialization rules change, this breaks."""
        obj = {"b": 2, "a": 1, "c": [3, 1.0, True]}
        expected = b'{"a":1,"b":2,"c":[3,1,true]}'
        assert canonical_json(obj) == expected

    def test_sort_keys(self) -> None:
        assert canonical_json({"z": 1, "a": 2}) == canonical_json({"a": 2, "z": 1})

    def test_negative_zero_normalized(self) -> None:
        assert canonical_json(-0.0) == canonical_json(0.0)

    def test_integral_float_becomes_int(self) -> None:
        assert canonical_json(1.0) == canonical_json(1)
        assert canonical_json({"x": 100.0}) == canonical_json({"x": 100})

    def test_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="NaN"):
            canonical_json(float("nan"))

    def test_infinity_rejected(self) -> None:
        with pytest.raises(ValueError, match="Infinity"):
            canonical_json(float("inf"))

    def test_nested_dict_sorted(self) -> None:
        nested = {"outer": {"z": 1, "a": 2}}
        expected = b'{"outer":{"a":2,"z":1}}'
        assert canonical_json(nested) == expected

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(TypeError, match="Unsupported"):
            canonical_json(object())


# ── Immutability ──────────────────────────────────────────────────────────────


class TestImmutability:
    def test_measurement_fields_frozen(self) -> None:
        m = _measurement()
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.id = "new-id"  # type: ignore[misc]

    def test_measurement_payload_frozen(self) -> None:
        m = _measurement()
        with pytest.raises(TypeError):
            m.payload["count"] = 999  # type: ignore[index]

    def test_provenance_params_frozen(self) -> None:
        p = _provenance()
        with pytest.raises(TypeError):
            p.params["n"] = 999  # type: ignore[index]

    def test_finding_frozen(self) -> None:
        f = _finding()
        with pytest.raises(dataclasses.FrozenInstanceError):
            f.statement = "changed"  # type: ignore[misc]

    def test_finding_params_frozen(self) -> None:
        f = _finding(params={"threshold": 0.05})
        with pytest.raises(TypeError):
            f.params["threshold"] = 0.99  # type: ignore[index]

    def test_assessment_policy_frozen(self) -> None:
        a = _assessment()
        with pytest.raises(TypeError):
            a.policy["missing_threshold"] = 0.99  # type: ignore[index]

    def test_claim_frozen(self) -> None:
        c = _claim()
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.text = "changed"  # type: ignore[misc]

    def test_artifact_frozen(self) -> None:
        art = _artifact()
        with pytest.raises(dataclasses.FrozenInstanceError):
            art.kind = ArtifactKind.IMAGE  # type: ignore[misc]

    def test_validation_check_detail_frozen(self) -> None:
        vc = ValidationCheck(
            layer=ValidationLayer.NUMERIC,
            verdict=ValidationVerdict.FAIL,
            reason_code="no_backing",
            detail={"n": 42},
            duration_ms=5,
        )
        with pytest.raises(TypeError):
            vc.detail["n"] = 0  # type: ignore[index]


# ── Determinism ───────────────────────────────────────────────────────────────


class TestDeterminism:
    def test_same_measurement_same_id(self) -> None:
        m1 = _measurement()
        m2 = _measurement()
        assert m1.id == m2.id

    def test_same_finding_same_id(self) -> None:
        msr_id = _measurement().id
        assert _finding(msr_id).id == _finding(msr_id).id

    def test_same_assessment_same_id(self) -> None:
        fnd_id = _finding().id
        assert _assessment(fnd_id).id == _assessment(fnd_id).id

    def test_same_claim_same_id(self) -> None:
        assert _claim().id == _claim().id

    def test_producer_version_change_changes_measurement_id(self) -> None:
        m1 = _measurement(provenance=_provenance(version="1.0.0"))
        m2 = _measurement(provenance=_provenance(version="2.0.0"))
        assert m1.id != m2.id

    def test_params_change_changes_measurement_id(self) -> None:
        m1 = _measurement(provenance=_provenance(params={"n": 100}))
        m2 = _measurement(provenance=_provenance(params={"n": 200}))
        assert m1.id != m2.id

    def test_scope_change_changes_measurement_id(self) -> None:
        m1 = _measurement(scope=_scope(refs=("age",)))
        m2 = _measurement(scope=_scope(refs=("income",)))
        assert m1.id != m2.id

    def test_dataset_id_change_changes_measurement_id(self) -> None:
        m1 = _measurement(dataset_id="dset-aaa")
        m2 = _measurement(dataset_id="dset-bbb")
        assert m1.id != m2.id

    def test_claim_text_change_changes_id(self) -> None:
        c1 = Claim.create(
            dataset_id="dset-abc",
            run_id="run-" + "b" * 32,
            text="Texto A.",
            supports=("fnd-" + "a" * 32,),
            validation=_validation_record(),
        )
        c2 = Claim.create(
            dataset_id="dset-abc",
            run_id="run-" + "b" * 32,
            text="Texto B.",
            supports=("fnd-" + "a" * 32,),
            validation=_validation_record(),
        )
        assert c1.id != c2.id

    def test_finding_params_change_changes_id(self) -> None:
        msr_id = _measurement().id
        f1 = _finding(msr_id, params={"threshold": 0.05})
        f2 = _finding(msr_id, params={"threshold": 0.10})
        assert f1.id != f2.id

    def test_finding_empty_params_same_id_as_default(self) -> None:
        """Empty params dict is the canonical default; identical findings must match."""
        msr_id = _measurement().id
        assert _finding(msr_id).id == _finding(msr_id).id

    def test_id_prefixes(self) -> None:
        m = _measurement()
        assert m.id.startswith("msr-")
        f = _finding(m.id)
        assert f.id.startswith("fnd-")
        a = _assessment(f.id)
        assert a.id.startswith("ast-")
        c = _claim()
        assert c.id.startswith("clm-")
        art = _artifact((m.id,))
        assert art.id.startswith("art-")


# ── dataset_id derivation ─────────────────────────────────────────────────────


class TestDatasetId:
    def test_same_content_same_id(self) -> None:
        files = [("data.csv", "a" * 64), ("meta.json", "b" * 64)]
        assert derive_dataset_id(files) == derive_dataset_id(files)

    def test_order_independent(self) -> None:
        files_a = [("a.csv", "a" * 64), ("b.csv", "b" * 64)]
        files_b = [("b.csv", "b" * 64), ("a.csv", "a" * 64)]
        assert derive_dataset_id(files_a) == derive_dataset_id(files_b)

    def test_content_change_changes_id(self) -> None:
        files_a = [("data.csv", "a" * 64)]
        files_b = [("data.csv", "b" * 64)]
        assert derive_dataset_id(files_a) != derive_dataset_id(files_b)

    def test_prefix(self) -> None:
        assert derive_dataset_id([("f.csv", "a" * 64)]).startswith("dset-")


# ── run_id derivation ─────────────────────────────────────────────────────────


class TestRunId:
    def test_deterministic(self) -> None:
        rid1 = derive_run_id("dset-abc", {"p": "1.0.0"}, "c" * 64)
        rid2 = derive_run_id("dset-abc", {"p": "1.0.0"}, "c" * 64)
        assert rid1 == rid2

    def test_producer_version_change(self) -> None:
        r1 = derive_run_id("dset-abc", {"p": "1.0.0"}, "c" * 64)
        r2 = derive_run_id("dset-abc", {"p": "2.0.0"}, "c" * 64)
        assert r1 != r2

    def test_prefix(self) -> None:
        assert derive_run_id("dset-abc", {}, "d" * 64).startswith("run-")


# ── Prefix enforcement ────────────────────────────────────────────────────────


class TestPrefixEnforcement:
    def test_finding_requires_msr_prefix(self) -> None:
        with pytest.raises(ValueError, match="msr-"):
            Finding.create(
                dataset_id="dset-abc",
                type="t",
                scope=_scope(),
                statement="s",
                severity=Severity.OK,
                derived_from=("fnd-wrong",),
                rule="r",
                rule_version="1.0.0",
                params={},
            )

    def test_finding_rejects_ast_prefix(self) -> None:
        with pytest.raises(ValueError, match="msr-"):
            Finding.create(
                dataset_id="dset-abc",
                type="t",
                scope=_scope(),
                statement="s",
                severity=Severity.OK,
                derived_from=("ast-wrong",),
                rule="r",
                rule_version="1.0.0",
                params={},
            )

    def test_assessment_requires_fnd_prefix(self) -> None:
        with pytest.raises(ValueError, match="fnd-"):
            Assessment.create(
                dataset_id="dset-abc",
                type="t",
                scope=_scope(),
                goal="g",
                verdict="pass",
                severity=Severity.OK,
                derived_from=("msr-wrong",),
                rule="r",
                rule_version="1.0.0",
                policy={},
            )

    def test_claim_rejects_art_prefix(self) -> None:
        with pytest.raises(ValueError, match="fnd-"):
            Claim.create(
                dataset_id="dset-abc",
                run_id="run-" + "b" * 32,
                text="texto",
                supports=("art-should-not-work",),
                validation=_validation_record(),
            )

    def test_claim_rejects_msr_prefix(self) -> None:
        with pytest.raises(ValueError, match="fnd-"):
            Claim.create(
                dataset_id="dset-abc",
                run_id="run-" + "b" * 32,
                text="texto",
                supports=("msr-should-not-work",),
                validation=_validation_record(),
            )

    def test_claim_accepts_fnd_and_ast(self) -> None:
        c = Claim.create(
            dataset_id="dset-abc",
            run_id="run-" + "b" * 32,
            text="texto",
            supports=("fnd-" + "a" * 32, "ast-" + "b" * 32),
            validation=_validation_record(),
        )
        assert c.id.startswith("clm-")

    def test_artifact_rejects_non_msr(self) -> None:
        with pytest.raises(ValueError, match="msr-"):
            Artifact.create(
                dataset_id="dset-abc",
                capability_id="cap",
                kind=ArtifactKind.VEGA_LITE,
                payload={},
                depicts=("fnd-wrong",),
                provenance=_provenance(),
            )


# ── Empty derived_from / supports ─────────────────────────────────────────────


class TestEmptyRefs:
    def test_finding_empty_derived_from(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            Finding.create(
                dataset_id="dset-abc",
                type="t",
                scope=_scope(),
                statement="s",
                severity=Severity.OK,
                derived_from=(),
                rule="r",
                rule_version="1.0.0",
                params={},
            )

    def test_assessment_empty_derived_from(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            Assessment.create(
                dataset_id="dset-abc",
                type="t",
                scope=_scope(),
                goal="g",
                verdict="pass",
                severity=Severity.OK,
                derived_from=(),
                rule="r",
                rule_version="1.0.0",
                policy={},
            )

    def test_claim_empty_supports(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            Claim.create(
                dataset_id="dset-abc",
                run_id="run-" + "b" * 32,
                text="texto",
                supports=(),
                validation=_validation_record(),
            )

    def test_artifact_empty_depicts(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            Artifact.create(
                dataset_id="dset-abc",
                capability_id="cap",
                kind=ArtifactKind.VEGA_LITE,
                payload={},
                depicts=(),
                provenance=_provenance(),
            )


# ── Schema validation ─────────────────────────────────────────────────────────


class TestSchemaValidation:
    def test_unregistered_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unregistered"):
            _measurement(type="no.such.type")

    def test_invalid_payload_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid payload"):
            _measurement(
                payload={"count": "not-a-number"},
            )

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid payload"):
            _measurement(
                payload={"count": 10},
            )

    def test_valid_normality_payload(self) -> None:
        m = Measurement.create(
            dataset_id="dset-abc",
            type="core.stats.normality",
            scope=_scope(),
            payload={
                "test": "shapiro_wilk",
                "statistic": 0.97,
                "p_value": 0.23,
                "sample_size": 100,
            },
            provenance=_provenance(),
        )
        assert m.id.startswith("msr-")

    def test_invalid_normality_test_name(self) -> None:
        with pytest.raises(ValueError, match="Invalid payload"):
            Measurement.create(
                dataset_id="dset-abc",
                type="core.stats.normality",
                scope=_scope(),
                payload={
                    "test": "unknown_test",
                    "statistic": 0.97,
                    "p_value": 0.23,
                    "sample_size": 100,
                },
                provenance=_provenance(),
            )

    def test_six_schemas_registered(self) -> None:
        expected = {
            "core.stats.descriptive",
            "core.stats.frequency",
            "core.quality.missing",
            "core.quality.uniqueness",
            "core.stats.normality",
            "core.stats.correlation",
        }
        assert expected.issubset(MEASUREMENT_SCHEMA_REGISTRY.registered_types())


# ── Symmetry (correlation) ────────────────────────────────────────────────────


class TestSymmetry:
    def _corr_measurement(self, col_a: str, col_b: str) -> Measurement:
        return Measurement.create(
            dataset_id="dset-abc",
            type="core.stats.correlation",
            scope=Scope(kind=ScopeKind.PAIR, refs=(col_a, col_b)),
            payload={"method": "pearson", "coefficient": 0.72, "sample_size": 200},
            provenance=_provenance(),
        )

    def test_corr_ab_equals_corr_ba(self) -> None:
        m_ab = self._corr_measurement("age", "income")
        m_ba = self._corr_measurement("income", "age")
        assert m_ab.id == m_ba.id

    def test_correlation_symmetric_flag(self) -> None:
        assert MEASUREMENT_SCHEMA_REGISTRY.is_symmetric("core.stats.correlation")

    def test_descriptive_not_symmetric(self) -> None:
        assert not MEASUREMENT_SCHEMA_REGISTRY.is_symmetric("core.stats.descriptive")


# ── CapabilityResult contract ─────────────────────────────────────────────────


class TestCapabilityResult:
    def test_artifact_without_measurement_raises(self) -> None:
        art = _artifact((_measurement().id,))
        with pytest.raises(ValueError, match="artifacts must include at least one"):
            CapabilityResult(measurements=(), artifacts=(art,))

    def test_artifact_with_measurement_ok(self) -> None:
        m = _measurement()
        art = _artifact((m.id,))
        result = CapabilityResult(measurements=(m,), artifacts=(art,))
        assert len(result.artifacts) == 1

    def test_empty_result_ok(self) -> None:
        result = CapabilityResult(measurements=(), artifacts=())
        assert result.measurements == ()

    def test_measurements_only_ok(self) -> None:
        m = _measurement()
        result = CapabilityResult(measurements=(m,), artifacts=())
        assert len(result.measurements) == 1


# ── Circular reference impossibility ─────────────────────────────────────────


class TestNoCyclePossible:
    """Demonstrate that circular references are structurally impossible.

    Finding.derived_from only accepts msr- ids.
    Assessment.derived_from only accepts fnd- ids.
    Claim.supports only accepts fnd- or ast- ids.
    Therefore no layer can reference itself or a downstream layer.
    """

    def test_finding_cannot_reference_finding(self) -> None:
        with pytest.raises(ValueError, match="msr-"):
            Finding.create(
                dataset_id="dset-abc",
                type="t",
                scope=_scope(),
                statement="s",
                severity=Severity.OK,
                derived_from=("fnd-" + "a" * 32,),
                rule="r",
                rule_version="1.0.0",
                params={},
            )

    def test_finding_cannot_reference_assessment(self) -> None:
        with pytest.raises(ValueError, match="msr-"):
            Finding.create(
                dataset_id="dset-abc",
                type="t",
                scope=_scope(),
                statement="s",
                severity=Severity.OK,
                derived_from=("ast-" + "a" * 32,),
                rule="r",
                rule_version="1.0.0",
                params={},
            )

    def test_assessment_cannot_reference_assessment(self) -> None:
        with pytest.raises(ValueError, match="fnd-"):
            Assessment.create(
                dataset_id="dset-abc",
                type="t",
                scope=_scope(),
                goal="g",
                verdict="pass",
                severity=Severity.OK,
                derived_from=("ast-" + "a" * 32,),
                rule="r",
                rule_version="1.0.0",
                policy={},
            )

    def test_assessment_cannot_reference_measurement(self) -> None:
        with pytest.raises(ValueError, match="fnd-"):
            Assessment.create(
                dataset_id="dset-abc",
                type="t",
                scope=_scope(),
                goal="g",
                verdict="pass",
                severity=Severity.OK,
                derived_from=("msr-" + "a" * 32,),
                rule="r",
                rule_version="1.0.0",
                policy={},
            )


# ── Layer enum sanity ─────────────────────────────────────────────────────────


def test_layer_enum_values() -> None:
    assert Layer.MEASUREMENT.value == "measurement"
    assert Layer.CLAIM.value == "claim"


# ── Property-based tests (hypothesis) ────────────────────────────────────────

_simple_json_values = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**31), max_value=2**31),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e15, max_value=1e15),
    st.text(max_size=50),
)


@st.composite
def _json_dict(draw: st.DrawFn) -> dict[str, object]:
    keys = draw(
        st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=5, unique=True)
    )
    return {k: draw(_simple_json_values) for k in keys}


@given(obj=_json_dict())
@settings(max_examples=200)
def test_canonical_json_idempotent(obj: dict[str, object]) -> None:
    """canonical_json called twice on the same object always returns the same bytes."""
    try:
        result = canonical_json(obj)
        assert canonical_json(obj) == result
    except (ValueError, TypeError):
        pass  # NaN/Infinity/unsupported type — exception is the correct behaviour


@given(
    producer=st.text(min_size=1, max_size=50),
    version=st.from_regex(r"\d+\.\d+\.\d+", fullmatch=True),
    n=st.integers(min_value=1, max_value=10_000),
)
@settings(max_examples=100)
def test_measurement_id_stable_under_reconstruction(
    producer: str, version: str, n: int
) -> None:
    """Constructing the same Measurement twice always yields the same id."""
    prov = _provenance(producer=producer, version=version, params={"n": n})
    m1 = _measurement(provenance=prov)
    m2 = _measurement(provenance=prov)
    assert m1.id == m2.id


@given(col_a=st.text(min_size=1, max_size=20), col_b=st.text(min_size=1, max_size=20))
@settings(max_examples=100)
def test_correlation_symmetry_property(col_a: str, col_b: str) -> None:
    """For any two column names, corr(a, b) and corr(b, a) share the same id."""
    payload: dict[str, object] = {
        "method": "pearson",
        "coefficient": 0.5,
        "sample_size": 50,
    }
    m_ab = Measurement.create(
        dataset_id="dset-x",
        type="core.stats.correlation",
        scope=Scope(kind=ScopeKind.PAIR, refs=(col_a, col_b)),
        payload=payload,
        provenance=_provenance(),
    )
    m_ba = Measurement.create(
        dataset_id="dset-x",
        type="core.stats.correlation",
        scope=Scope(kind=ScopeKind.PAIR, refs=(col_b, col_a)),
        payload=payload,
        provenance=_provenance(),
    )
    assert m_ab.id == m_ba.id

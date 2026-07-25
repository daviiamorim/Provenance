"""Test suite for core/rules — Etapa 3.

Covers:
  - Each Finding rule: fires, does not fire, boundary input.
  - Normality rule specifically: W-based decision is p-value-independent;
    normal-rounded-to-int with large-sample low p-value still gives ok.
  - Determinism: same input -> same Finding/Assessment id.
  - rule_version change -> different id.
  - Goal dependency: same Findings -> different Assessments for different goals.
  - Rule that decides not to emit (variable_association for |r| < threshold).
  - Assessment verdict labels per goal.
  - ok Findings are emitted as positive evidence (duplicate_rate always emits).
"""

from __future__ import annotations

import numpy as np
from scipy import stats as scipy_stats

from core.model import (
    Assessment,
    Finding,
    Measurement,
    Provenance,
    Scope,
    ScopeKind,
    Severity,
)
from core.rules import RULE_REGISTRY
from core.rules.assessment._data_quality import DataQualityRule
from core.rules.assessment._modeling_readiness import ModelingReadinessRule
from core.rules.finding._category_balance import CategoryBalanceRule
from core.rules.finding._distribution_shape import DistributionShapeRule
from core.rules.finding._duplicate_rate import DuplicateRateRule
from core.rules.finding._missing_rate import MissingRateRule
from core.rules.finding._variable_association import VariableAssociationRule

# ── shared fixtures ───────────────────────────────────────────────────────────

DATASET_ID = "dset-test00000000000000000000000000"


def _prov(*, null_sentinels: list[str] | None = None) -> Provenance:
    params: dict[str, object] = {}
    if null_sentinels is not None:
        params["null_sentinels"] = null_sentinels
    return Provenance(
        producer="test.producer",
        version="1.0.0",
        params=params,
        input_digest="a" * 64,
        duration_ms=1,
        seed=None,
    )


def _col_scope(col: str) -> Scope:
    return Scope(kind=ScopeKind.COLUMN, refs=(col,))


def _pair_scope(a: str, b: str) -> Scope:
    return Scope(kind=ScopeKind.PAIR, refs=(a, b))


def _normality_msr(
    col: str,
    *,
    test: str,
    statistic: float,
    p_value: float,
    sample_size: int,
) -> Measurement:
    return Measurement.create(
        dataset_id=DATASET_ID,
        type="core.stats.normality",
        scope=_col_scope(col),
        payload={
            "test": test,
            "statistic": statistic,
            "p_value": p_value,
            "sample_size": sample_size,
        },
        provenance=_prov(),
    )


def _descriptive_msr(
    col: str,
    *,
    count: int = 100,
    mean: float = 0.0,
    skewness: float | None = None,
    excess_kurtosis: float | None = None,
) -> Measurement:
    payload: dict[str, object] = {
        "count": count,
        "mean": mean,
        "std": 1.0,
        "min": -3.0,
        "max": 3.0,
        "q25": -0.67,
        "q50": 0.0,
        "q75": 0.67,
    }
    if skewness is not None:
        payload["skewness"] = skewness
    if excess_kurtosis is not None:
        payload["excess_kurtosis"] = excess_kurtosis
    return Measurement.create(
        dataset_id=DATASET_ID,
        type="core.stats.descriptive",
        scope=_col_scope(col),
        payload=payload,
        provenance=_prov(),
    )


def _missing_msr(
    col: str,
    *,
    total: int,
    missing: int,
    sentinels: list[str] | None = None,
) -> Measurement:
    return Measurement.create(
        dataset_id=DATASET_ID,
        type="core.quality.missing",
        scope=_col_scope(col),
        payload={
            "total_count": total,
            "missing_count": missing,
            "missing_proportion": missing / total if total > 0 else 0.0,
        },
        provenance=_prov(null_sentinels=sentinels),
    )


def _uniqueness_msr(
    col: str,
    *,
    total: int,
    unique: int,
    duplicates: int,
    null_count: int = 0,
) -> Measurement:
    valid = total - null_count
    payload: dict[str, object] = {
        "total_count": total,
        "unique_count": unique,
        "duplicate_count": duplicates,
        "unique_proportion": unique / valid if valid > 0 else 0.0,
    }
    if null_count > 0:
        payload["null_count"] = null_count
    return Measurement.create(
        dataset_id=DATASET_ID,
        type="core.quality.uniqueness",
        scope=_col_scope(col),
        payload=payload,
        provenance=_prov(),
    )


def _frequency_msr(col: str, *, frequencies: list[tuple[object, int]]) -> Measurement:
    total = sum(c for _, c in frequencies)
    freqs = [
        {"value": v, "count": c, "proportion": c / total if total > 0 else 0.0}
        for v, c in sorted(frequencies, key=lambda x: x[1], reverse=True)
    ]
    return Measurement.create(
        dataset_id=DATASET_ID,
        type="core.stats.frequency",
        scope=_col_scope(col),
        payload={"total_count": total, "frequencies": freqs},
        provenance=_prov(),
    )


def _correlation_msr(col_a: str, col_b: str, *, r: float, n: int) -> Measurement:
    return Measurement.create(
        dataset_id=DATASET_ID,
        type="core.stats.correlation",
        scope=_pair_scope(col_a, col_b),
        payload={
            "method": "pearson", "coefficient": r, "p_value": 0.001, "sample_size": n
        },
        provenance=_prov(),
    )


def _run_finding_rule(rule_cls: type, measurements: list[Measurement]) -> list[Finding]:
    return rule_cls().evaluate(DATASET_ID, measurements)  # type: ignore[no-any-return]


# ── DistributionShapeRule ─────────────────────────────────────────────────────


class TestDistributionShapeRule:
    rule = DistributionShapeRule()

    # ── Shapiro-Wilk path ─────────────────────────────────────────────────────

    def _sw(self, col: str, w: float, p: float, n: int) -> Measurement:
        return _normality_msr(
            col, test="shapiro_wilk", statistic=w, p_value=p, sample_size=n
        )

    def _dag(self, col: str, k2: float, p: float, n: int) -> Measurement:
        return _normality_msr(
            col, test="dagostino_pearson", statistic=k2, p_value=p, sample_size=n
        )

    def test_sw_high_w_gives_ok(self) -> None:
        findings = self.rule.evaluate(DATASET_ID, [self._sw("age", 0.98, 0.45, 100)])
        assert len(findings) == 1
        assert findings[0].severity == Severity.OK

    def test_sw_low_p_high_w_still_ok(self) -> None:
        """Key regression: p=0.00007 with W=0.97 must still be ok.

        This is the 'idade' case from the demo — a truly normal distribution
        rounded to integers; statistical significance inflated by sample size.
        The rule must use W, not p_value.
        """
        findings = self.rule.evaluate(
            DATASET_ID, [self._sw("idade", 0.97, 0.00007, 912)]
        )
        assert len(findings) == 1
        assert findings[0].severity == Severity.OK

    def test_sw_borderline_w_gives_warn(self) -> None:
        findings = self.rule.evaluate(DATASET_ID, [self._sw("x", 0.92, 0.01, 200)])
        assert findings[0].severity == Severity.WARN

    def test_sw_low_w_gives_fail(self) -> None:
        findings = self.rule.evaluate(DATASET_ID, [self._sw("x", 0.80, 0.0001, 300)])
        assert findings[0].severity == Severity.FAIL

    def test_sw_boundary_exactly_at_ok_threshold(self) -> None:
        findings = self.rule.evaluate(DATASET_ID, [self._sw("x", 0.95, 0.05, 50)])
        assert findings[0].severity == Severity.OK

    def test_sw_boundary_just_below_ok_threshold(self) -> None:
        findings = self.rule.evaluate(DATASET_ID, [self._sw("x", 0.9499, 0.04, 50)])
        assert findings[0].severity == Severity.WARN

    def test_sw_thresholds_visible_in_params(self) -> None:
        f = self.rule.evaluate(DATASET_ID, [self._sw("x", 0.97, 0.3, 100)])[0]
        assert "threshold_ok" in f.params
        assert "threshold_warn" in f.params
        assert f.params["statistic_w"] == 0.97

    # ── D'Agostino path ───────────────────────────────────────────────────────

    def test_dagostino_low_skew_kurt_gives_ok(self) -> None:
        norm_m = self._dag("big", 5.0, 0.08, 6000)
        desc_m = _descriptive_msr("big", count=6000, skewness=0.1, excess_kurtosis=0.2)
        findings = self.rule.evaluate(DATASET_ID, [norm_m, desc_m])
        assert findings[0].severity == Severity.OK

    def test_dagostino_high_skewness_gives_fail(self) -> None:
        norm_m = self._dag("big", 200.0, 0.0, 8000)
        desc_m = _descriptive_msr("big", count=8000, skewness=2.5, excess_kurtosis=0.3)
        findings = self.rule.evaluate(DATASET_ID, [norm_m, desc_m])
        assert findings[0].severity == Severity.FAIL

    def test_dagostino_without_descriptive_emits_nothing(self) -> None:
        norm_m = self._dag("big", 50.0, 0.001, 6000)
        findings = self.rule.evaluate(DATASET_ID, [norm_m])
        assert findings == []

    def test_dagostino_without_skewness_field_emits_nothing(self) -> None:
        norm_m = self._dag("big", 50.0, 0.001, 6000)
        desc_m = _descriptive_msr("big", count=6000)  # no skewness/kurtosis fields
        findings = self.rule.evaluate(DATASET_ID, [norm_m, desc_m])
        assert findings == []

    def test_dagostino_thresholds_visible_in_params(self) -> None:
        norm_m = self._dag("big", 5.0, 0.08, 6000)
        desc_m = _descriptive_msr("big", count=6000, skewness=0.2, excess_kurtosis=0.4)
        f = self.rule.evaluate(DATASET_ID, [norm_m, desc_m])[0]
        assert "skewness_threshold_ok" in f.params
        assert "excess_kurtosis_threshold_ok" in f.params

    # ── Real-distribution integration test ───────────────────────────────────

    def test_normal_rounded_to_int_classified_as_normal(self) -> None:
        """Normal data rounded to integer produces high W — rule must say ok.

        The p-value is not asserted: for moderate N it may or may not be small.
        test_sw_low_p_high_w_still_ok covers the specific case where p is tiny
        but W is high.  This test verifies the happy-path integration: genuine
        normal data goes in, correct ok verdict comes out, W drives the decision.
        """
        rng = np.random.default_rng(42)
        data = np.round(rng.normal(loc=50, scale=10, size=1000)).astype(float)
        w_stat, p_val = scipy_stats.shapiro(data)
        assert w_stat >= 0.95, (
            f"W={w_stat:.4f} — normally distributed data should have high W"
        )

        m = _normality_msr("age_int", test="shapiro_wilk", statistic=float(w_stat),
                           p_value=float(p_val), sample_size=len(data))
        findings = self.rule.evaluate(DATASET_ID, [m])
        assert findings[0].severity == Severity.OK

    def test_clearly_asymmetric_distribution_gives_fail(self) -> None:
        """Exponential distribution is clearly non-normal; rule must say fail."""
        rng = np.random.default_rng(42)
        data = rng.exponential(scale=1.0, size=200).astype(float)
        w_stat, p_val = scipy_stats.shapiro(data)
        # Exponential has skewness=2, kurtosis=6; W should be well below 0.90
        m = _normality_msr("income", test="shapiro_wilk", statistic=float(w_stat),
                           p_value=float(p_val), sample_size=len(data))
        findings = self.rule.evaluate(DATASET_ID, [m])
        assert findings[0].severity == Severity.FAIL

    # ── Determinism and versioning ────────────────────────────────────────────

    def test_determinism(self) -> None:
        m = _normality_msr(
            "x", test="shapiro_wilk", statistic=0.96, p_value=0.2, sample_size=100
        )
        f1 = self.rule.evaluate(DATASET_ID, [m])[0]
        f2 = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f1.id == f2.id

    def test_rule_version_change_changes_id(self) -> None:
        m = _normality_msr(
            "x", test="shapiro_wilk", statistic=0.96, p_value=0.2, sample_size=100
        )

        class NewVersionRule(DistributionShapeRule):
            rule_version = "2.0.0"

        f1 = self.rule.evaluate(DATASET_ID, [m])[0]
        f2 = NewVersionRule().evaluate(DATASET_ID, [m])[0]
        assert f1.id != f2.id

    def test_unknown_test_emits_nothing(self) -> None:
        m = Measurement.create(
            dataset_id=DATASET_ID,
            type="core.stats.normality",
            scope=_col_scope("x"),
            payload={
                "test": "kolmogorov_smirnov",
                "statistic": 0.05,
                "p_value": 0.5,
                "sample_size": 100,
            },
            provenance=_prov(),
        )
        assert self.rule.evaluate(DATASET_ID, [m]) == []


# ── MissingRateRule ───────────────────────────────────────────────────────────


class TestMissingRateRule:
    rule = MissingRateRule()

    def test_zero_missing_gives_ok(self) -> None:
        m = _missing_msr("age", total=100, missing=0)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.severity == Severity.OK

    def test_low_missing_gives_warn(self) -> None:
        m = _missing_msr("age", total=100, missing=3)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.severity == Severity.WARN

    def test_high_missing_gives_fail(self) -> None:
        m = _missing_msr("age", total=100, missing=20)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.severity == Severity.FAIL

    def test_boundary_exactly_at_5pct_is_warn(self) -> None:
        m = _missing_msr("x", total=100, missing=5)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.severity == Severity.WARN

    def test_boundary_just_above_5pct_is_fail(self) -> None:
        m = _missing_msr("x", total=100, missing=6)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.severity == Severity.FAIL

    def test_sentinels_visible_in_params(self) -> None:
        m = _missing_msr("x", total=100, missing=10, sentinels=["", "N/A"])
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.params["null_sentinels_applied"] == ["", "N/A"]

    def test_threshold_visible_in_params(self) -> None:
        m = _missing_msr("x", total=100, missing=10)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert "warn_threshold" in f.params

    def test_determinism(self) -> None:
        m = _missing_msr("x", total=100, missing=10)
        f1 = self.rule.evaluate(DATASET_ID, [m])[0]
        f2 = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f1.id == f2.id

    def test_no_measurements_emits_nothing(self) -> None:
        assert self.rule.evaluate(DATASET_ID, []) == []

    def test_wrong_measurement_type_ignored(self) -> None:
        m = _descriptive_msr("x")
        assert self.rule.evaluate(DATASET_ID, [m]) == []


# ── CategoryBalanceRule ───────────────────────────────────────────────────────


class TestCategoryBalanceRule:
    rule = CategoryBalanceRule()

    def _make_cat(
        self, col: str, *, counts: list[int]
    ) -> tuple[Measurement, Measurement]:
        unique = len(counts)
        total = sum(counts)
        freqs: list[tuple[object, int]] = [(str(i), c) for i, c in enumerate(counts)]
        return (
            _frequency_msr(col, frequencies=freqs),
            _uniqueness_msr(col, total=total, unique=unique, duplicates=total - unique),
        )

    def test_balanced_gives_ok(self) -> None:
        freq_m, uniq_m = self._make_cat("cat", counts=[50, 50])
        findings = self.rule.evaluate(DATASET_ID, [freq_m, uniq_m])
        assert len(findings) == 1
        assert findings[0].severity == Severity.OK

    def test_moderate_imbalance_gives_warn(self) -> None:
        freq_m, uniq_m = self._make_cat("cat", counts=[70, 30])
        findings = self.rule.evaluate(DATASET_ID, [freq_m, uniq_m])
        assert findings[0].severity == Severity.WARN

    def test_severe_imbalance_gives_fail(self) -> None:
        # 6:1 ratio — the demo case
        freq_m, uniq_m = self._make_cat("cat", counts=[600, 100])
        findings = self.rule.evaluate(DATASET_ID, [freq_m, uniq_m])
        assert findings[0].severity == Severity.FAIL

    def test_single_class_gives_fail(self) -> None:
        freq_m, uniq_m = self._make_cat("cat", counts=[100])
        findings = self.rule.evaluate(DATASET_ID, [freq_m, uniq_m])
        assert findings[0].severity == Severity.FAIL

    def test_boundary_exactly_at_fail_threshold(self) -> None:
        # top_proportion = 0.80 → >0.80 is fail, exactly 0.80 is warn
        freq_m, uniq_m = self._make_cat("cat", counts=[80, 20])
        findings = self.rule.evaluate(DATASET_ID, [freq_m, uniq_m])
        assert findings[0].severity == Severity.WARN

    def test_non_categorical_column_emits_nothing(self) -> None:
        """Continuous-looking column: high unique_rate, many unique values."""
        n = 1000
        freq_m = _frequency_msr("income", frequencies=[(str(i), 1) for i in range(n)])
        uniq_m = _uniqueness_msr("income", total=n, unique=n, duplicates=0)
        findings = self.rule.evaluate(DATASET_ID, [freq_m, uniq_m])
        assert findings == []

    def test_thresholds_visible_in_params(self) -> None:
        freq_m, uniq_m = self._make_cat("cat", counts=[60, 40])
        f = self.rule.evaluate(DATASET_ID, [freq_m, uniq_m])[0]
        assert "warn_threshold" in f.params
        assert "fail_threshold" in f.params

    def test_determinism(self) -> None:
        freq_m, uniq_m = self._make_cat("cat", counts=[600, 100])
        f1 = self.rule.evaluate(DATASET_ID, [freq_m, uniq_m])[0]
        f2 = self.rule.evaluate(DATASET_ID, [freq_m, uniq_m])[0]
        assert f1.id == f2.id

    def test_missing_uniqueness_measurement_emits_nothing(self) -> None:
        freq_m = _frequency_msr("cat", frequencies=[("A", 80), ("B", 20)])
        assert self.rule.evaluate(DATASET_ID, [freq_m]) == []


# ── DuplicateRateRule ─────────────────────────────────────────────────────────


class TestDuplicateRateRule:
    rule = DuplicateRateRule()

    def test_zero_duplicates_gives_ok(self) -> None:
        m = _uniqueness_msr("id", total=100, unique=100, duplicates=0)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.severity == Severity.OK

    def test_low_duplicate_rate_gives_warn(self) -> None:
        m = _uniqueness_msr("id", total=100, unique=99, duplicates=1)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.severity == Severity.WARN

    def test_high_duplicate_rate_gives_fail(self) -> None:
        m = _uniqueness_msr("id", total=100, unique=90, duplicates=10)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.severity == Severity.FAIL

    def test_boundary_exactly_at_1pct_is_warn(self) -> None:
        m = _uniqueness_msr("x", total=100, unique=99, duplicates=1)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.severity == Severity.WARN

    def test_boundary_just_above_1pct_is_fail(self) -> None:
        m = _uniqueness_msr("x", total=100, unique=98, duplicates=2)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.severity == Severity.FAIL

    def test_always_emits_even_for_ok(self) -> None:
        """ok Finding is positive evidence that the check passed."""
        m = _uniqueness_msr("id", total=50, unique=50, duplicates=0)
        findings = self.rule.evaluate(DATASET_ID, [m])
        assert len(findings) == 1

    def test_threshold_visible_in_params(self) -> None:
        m = _uniqueness_msr("id", total=100, unique=95, duplicates=5)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert "warn_threshold" in f.params
        assert "duplicate_rate" in f.params

    def test_determinism(self) -> None:
        m = _uniqueness_msr("id", total=100, unique=95, duplicates=5)
        f1 = self.rule.evaluate(DATASET_ID, [m])[0]
        f2 = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f1.id == f2.id


# ── VariableAssociationRule ───────────────────────────────────────────────────


class TestVariableAssociationRule:
    rule = VariableAssociationRule()

    def test_weak_correlation_emits_nothing(self) -> None:
        m = _correlation_msr("a", "b", r=0.2, n=100)
        assert self.rule.evaluate(DATASET_ID, [m]) == []

    def test_exactly_at_emit_threshold_emits_nothing(self) -> None:
        # |r| = 0.3 means abs_r >= threshold is False for < 0.3 check;
        # but 0.3 >= 0.3 means it DOES emit
        m = _correlation_msr("a", "b", r=0.3, n=100)
        findings = self.rule.evaluate(DATASET_ID, [m])
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARN

    def test_just_below_emit_threshold_emits_nothing(self) -> None:
        m = _correlation_msr("a", "b", r=0.29, n=100)
        assert self.rule.evaluate(DATASET_ID, [m]) == []

    def test_moderate_correlation_gives_warn(self) -> None:
        m = _correlation_msr("a", "b", r=0.5, n=200)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.severity == Severity.WARN

    def test_strong_correlation_gives_fail(self) -> None:
        m = _correlation_msr("a", "b", r=0.85, n=300)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.severity == Severity.FAIL

    def test_strong_negative_correlation_gives_fail(self) -> None:
        m = _correlation_msr("a", "b", r=-0.80, n=300)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.severity == Severity.FAIL

    def test_boundary_exactly_at_fail_threshold(self) -> None:
        m = _correlation_msr("a", "b", r=0.7, n=100)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f.severity == Severity.FAIL

    def test_thresholds_visible_in_params(self) -> None:
        m = _correlation_msr("a", "b", r=0.5, n=100)
        f = self.rule.evaluate(DATASET_ID, [m])[0]
        assert "emit_threshold" in f.params
        assert "fail_threshold" in f.params

    def test_determinism(self) -> None:
        m = _correlation_msr("a", "b", r=0.75, n=200)
        f1 = self.rule.evaluate(DATASET_ID, [m])[0]
        f2 = self.rule.evaluate(DATASET_ID, [m])[0]
        assert f1.id == f2.id


# ── Assessment rules ──────────────────────────────────────────────────────────


def _make_finding(
    type_: str, severity: Severity, msr_id: str = "msr-" + "a" * 32
) -> Finding:
    return Finding.create(
        dataset_id=DATASET_ID,
        type=type_,
        scope=Scope(kind=ScopeKind.COLUMN, refs=("col",)),
        statement="test statement",
        severity=severity,
        derived_from=(msr_id,),
        rule="test.rule",
        rule_version="1.0.0",
        params={},
    )


class TestModelingReadinessRule:
    rule = ModelingReadinessRule()

    def _run(self, findings: list[Finding]) -> Assessment | None:
        return self.rule.evaluate(DATASET_ID, "modeling_readiness", findings)

    def test_all_ok_gives_eligible(self) -> None:
        findings = [
            _make_finding("core.finding.missing_rate", Severity.OK),
            _make_finding("core.finding.duplicate_rate", Severity.OK),
        ]
        assessment = self._run(findings)
        assert assessment is not None
        assert assessment.severity == Severity.OK
        assert assessment.verdict == "eligible"

    def test_missing_rate_fail_gives_not_eligible(self) -> None:
        findings = [_make_finding("core.finding.missing_rate", Severity.FAIL)]
        assessment = self._run(findings)
        assert assessment is not None
        assert assessment.severity == Severity.FAIL
        assert assessment.verdict == "not_eligible"

    def test_category_balance_fail_gives_not_eligible(self) -> None:
        findings = [_make_finding("core.finding.category_balance", Severity.FAIL)]
        assessment = self._run(findings)
        assert assessment is not None
        assert assessment.severity == Severity.FAIL

    def test_distribution_shape_fail_gives_needs_attention(self) -> None:
        """Non-normality is a warn trigger, not a fail trigger, for modeling."""
        findings = [_make_finding("core.finding.distribution_shape", Severity.FAIL)]
        assessment = self._run(findings)
        assert assessment is not None
        assert assessment.severity == Severity.WARN
        assert assessment.verdict == "needs_attention"

    def test_wrong_goal_returns_none(self) -> None:
        findings = [_make_finding("core.finding.missing_rate", Severity.FAIL)]
        result = self.rule.evaluate(DATASET_ID, "data_quality", findings)
        assert result is None

    def test_no_relevant_findings_returns_none(self) -> None:
        findings = [_make_finding("core.finding.duplicate_rate", Severity.OK)]
        result = self._run(findings)
        assert result is None

    def test_policy_visible_on_assessment(self) -> None:
        findings = [_make_finding("core.finding.missing_rate", Severity.OK)]
        assessment = self._run(findings)
        assert assessment is not None
        assert "fail_on_finding_types" in assessment.policy

    def test_determinism(self) -> None:
        findings = [_make_finding("core.finding.missing_rate", Severity.FAIL)]
        a1 = self._run(findings)
        a2 = self._run(findings)
        assert a1 is not None
        assert a2 is not None
        assert a1.id == a2.id


class TestDataQualityRule:
    rule = DataQualityRule()

    def _run(self, findings: list[Finding]) -> Assessment | None:
        return self.rule.evaluate(DATASET_ID, "data_quality", findings)

    def test_all_ok_gives_acceptable(self) -> None:
        findings = [
            _make_finding("core.finding.missing_rate", Severity.OK),
            _make_finding("core.finding.duplicate_rate", Severity.OK),
        ]
        assessment = self._run(findings)
        assert assessment is not None
        assert assessment.verdict == "acceptable"

    def test_missing_fail_gives_unacceptable(self) -> None:
        findings = [_make_finding("core.finding.missing_rate", Severity.FAIL)]
        assessment = self._run(findings)
        assert assessment is not None
        assert assessment.verdict == "unacceptable"

    def test_duplicate_warn_gives_marginal(self) -> None:
        findings = [_make_finding("core.finding.duplicate_rate", Severity.WARN)]
        assessment = self._run(findings)
        assert assessment is not None
        assert assessment.verdict == "marginal"

    def test_wrong_goal_returns_none(self) -> None:
        findings = [_make_finding("core.finding.missing_rate", Severity.FAIL)]
        result = self.rule.evaluate(DATASET_ID, "modeling_readiness", findings)
        assert result is None


# ── Goal dependency: same Findings → different Assessments ───────────────────


class TestGoalDependency:
    """The same set of Findings must produce different Assessments for
    different goals — this is the core distinction between Finding and Assessment.
    """

    def test_category_balance_fail_affects_only_modeling(self) -> None:
        """6:1 imbalance → modeling_readiness fails, data_quality stays ok."""
        findings = [
            _make_finding("core.finding.category_balance", Severity.FAIL),
            _make_finding("core.finding.missing_rate", Severity.OK),
            _make_finding("core.finding.duplicate_rate", Severity.OK),
        ]
        modeling = ModelingReadinessRule().evaluate(
            DATASET_ID, "modeling_readiness", findings
        )
        quality = DataQualityRule().evaluate(DATASET_ID, "data_quality", findings)

        assert modeling is not None
        assert modeling.severity == Severity.FAIL
        assert quality is not None
        assert quality.severity == Severity.OK

    def test_same_findings_produce_different_assessment_ids(self) -> None:
        """Two goals, same input Findings — IDs must differ."""
        findings = [_make_finding("core.finding.missing_rate", Severity.OK)]
        modeling = ModelingReadinessRule().evaluate(
            DATASET_ID, "modeling_readiness", findings
        )
        quality = DataQualityRule().evaluate(DATASET_ID, "data_quality", findings)
        assert modeling is not None
        assert quality is not None
        assert modeling.id != quality.id

    def test_rule_version_change_changes_assessment_id(self) -> None:
        findings = [_make_finding("core.finding.missing_rate", Severity.OK)]

        class V2Rule(ModelingReadinessRule):
            rule_version = "2.0.0"

        a1 = ModelingReadinessRule().evaluate(
            DATASET_ID, "modeling_readiness", findings
        )
        a2 = V2Rule().evaluate(DATASET_ID, "modeling_readiness", findings)
        assert a1 is not None
        assert a2 is not None
        assert a1.id != a2.id


# ── RULE_REGISTRY integration ─────────────────────────────────────────────────


class TestRuleRegistry:
    def test_finding_rules_registered(self) -> None:
        names = {r.rule for r in RULE_REGISTRY.finding_rules()}
        expected = {
            "core.finding.distribution_shape",
            "core.finding.missing_rate",
            "core.finding.category_balance",
            "core.finding.duplicate_rate",
            "core.finding.variable_association",
        }
        assert expected.issubset(names)

    def test_assessment_rules_registered(self) -> None:
        names = {r.rule for r in RULE_REGISTRY.assessment_rules()}
        assert "core.assessment.modeling_readiness" in names
        assert "core.assessment.data_quality" in names

    def test_run_findings_end_to_end(self) -> None:
        measurements = [
            _missing_msr("age", total=100, missing=0),
            _uniqueness_msr("age", total=100, unique=95, duplicates=5),
        ]
        findings = RULE_REGISTRY.run_findings(DATASET_ID, measurements)
        types = {f.type for f in findings}
        assert "core.finding.missing_rate" in types
        assert "core.finding.duplicate_rate" in types

    def test_run_assessments_end_to_end(self) -> None:
        findings = [
            _make_finding("core.finding.missing_rate", Severity.OK),
            _make_finding("core.finding.duplicate_rate", Severity.OK),
        ]
        assessments = RULE_REGISTRY.run_assessments(
            DATASET_ID, "data_quality", findings
        )
        assert len(assessments) == 1
        assert assessments[0].goal == "data_quality"

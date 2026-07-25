"""Statement fidelity tests — Finding.params must mirror Measurement.payload.

Guarantee: every number embedded by a Finding rule in Finding.statement is also
stored in Finding.params, and every number in Finding.params is either taken
directly from the source Measurement.payload or is a rule constant (threshold).

This is the verification mechanism described in the design review: fidelity
Finding→Measurement is checked here at test time, not pushed to the Validator.
The consequence: the Validator's numeric layer can safely compare claim numbers
against Finding.params (without accessing Measurements directly) because those
params are guaranteed to be faithful copies of the Measurement values.

Each test class covers one Finding rule:
  - Creates a Measurement with a known payload
  - Calls rule.evaluate()
  - Asserts Finding.params contains the exact measurement-derived values
  - Asserts Finding.params contains the rule threshold constants
"""

from __future__ import annotations

import re
from collections.abc import Mapping as ABCMapping

from core.model import Measurement, Provenance, Scope, ScopeKind
from core.rules.finding._category_balance import CategoryBalanceRule
from core.rules.finding._distribution_shape import DistributionShapeRule
from core.rules.finding._duplicate_rate import DuplicateRateRule
from core.rules.finding._missing_rate import MissingRateRule
from core.rules.finding._variable_association import VariableAssociationRule

DATASET_ID = "dset-test00000000000000000000000000"
_TOL = 1e-9  # exact floating-point equality (same Python float object)


def _prov() -> Provenance:
    return Provenance(
        producer="test.producer",
        version="1.0.0",
        params={},
        input_digest="a" * 64,
        duration_ms=1,
        seed=None,
    )


def _col(col: str) -> Scope:
    return Scope(kind=ScopeKind.COLUMN, refs=(col,))


def _pair(a: str, b: str) -> Scope:
    return Scope(kind=ScopeKind.PAIR, refs=(a, b))


# ── US-format number extractor for statement verification ─────────────────────
# Finding statements use Python f-strings (US decimal format: period separator).
_STMT_NUM_RE = re.compile(r"(?<![.\d\w])-?(\d+(?:\.\d+)?)(\s*%)?(?!\d)")


def _extract_stmt_numbers(text: str) -> list[tuple[float, bool]]:
    """Extract (value, is_pct) from a US-format statement string."""
    results: list[tuple[float, bool]] = []
    for m in _STMT_NUM_RE.finditer(text):
        try:
            value = float(m.group(1))
        except ValueError:
            continue
        is_pct = bool(m.group(2) and m.group(2).strip() == "%")
        results.append((value, is_pct))
    return results


def _all_numeric_params(params: object) -> list[float]:
    """Flatten all numeric values from params recursively.

    Handles dict, MappingProxyType (ABCMapping), list, and tuple.
    """
    values: list[float] = []

    def _recurse(obj: object) -> None:
        if isinstance(obj, bool):
            return
        if isinstance(obj, (int, float)):
            values.append(float(obj))
        elif isinstance(obj, ABCMapping):
            for v in obj.values():
                _recurse(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _recurse(item)

    _recurse(params)
    return values


def _assert_statement_numbers_in_params(
    statement: str,
    params: object,
    *,
    tolerance: float = 0.005,
) -> None:
    """Assert every number in statement is traceable to params (within tolerance)."""
    stmt_nums = _extract_stmt_numbers(statement)
    param_nums = _all_numeric_params(params)

    for value, is_pct in stmt_nums:
        candidates = [value]
        if is_pct:
            candidates.append(value / 100.0)
        matched = any(abs(c - p) <= tolerance for c in candidates for p in param_nums)
        assert matched, (
            f"Number {value}{'%' if is_pct else ''} in statement "
            f"'{statement}' not found in params {dict(params)}."  # type: ignore[call-overload]
        )


# ── MissingRateRule ───────────────────────────────────────────────────────────


class TestMissingRateFidelity:
    def _msr(self, *, total: int, missing: int) -> Measurement:
        return Measurement.create(
            dataset_id=DATASET_ID,
            type="core.quality.missing",
            scope=_col("income"),
            payload={
                "total_count": total,
                "missing_count": missing,
                "missing_proportion": missing / total if total else 0.0,
            },
            provenance=_prov(),
        )

    def test_params_mirror_payload_on_fail(self) -> None:
        m = self._msr(total=912, missing=69)
        fnds = MissingRateRule().evaluate(DATASET_ID, [m])
        assert fnds
        f = fnds[0]
        assert f.params["total_count"] == 912
        assert f.params["missing_count"] == 69
        assert abs(float(f.params["missing_proportion"]) - 69 / 912) < _TOL  # type: ignore[arg-type]

    def test_params_contains_threshold(self) -> None:
        m = self._msr(total=100, missing=10)
        f = MissingRateRule().evaluate(DATASET_ID, [m])[0]
        assert "warn_threshold" in f.params

    def test_statement_numbers_traceable_to_params(self) -> None:
        m = self._msr(total=912, missing=69)
        f = MissingRateRule().evaluate(DATASET_ID, [m])[0]
        _assert_statement_numbers_in_params(f.statement, f.params)

    def test_zero_missing_params_correct(self) -> None:
        m = self._msr(total=100, missing=0)
        f = MissingRateRule().evaluate(DATASET_ID, [m])[0]
        assert f.params["missing_count"] == 0
        assert f.params["missing_proportion"] == 0.0

    def test_statement_numbers_traceable_on_ok(self) -> None:
        m = self._msr(total=100, missing=0)
        f = MissingRateRule().evaluate(DATASET_ID, [m])[0]
        _assert_statement_numbers_in_params(f.statement, f.params)


# ── DuplicateRateRule ─────────────────────────────────────────────────────────


class TestDuplicateRateFidelity:
    def _msr(self, *, total: int, duplicate: int) -> Measurement:
        unique = total - duplicate
        return Measurement.create(
            dataset_id=DATASET_ID,
            type="core.quality.row_dedup",
            scope=Scope(kind=ScopeKind.DATASET, refs=(DATASET_ID,)),
            payload={
                "total_rows": total,
                "unique_rows": unique,
                "duplicate_rows": duplicate,
                "duplicate_proportion": duplicate / total if total else 0.0,
            },
            provenance=_prov(),
        )

    def test_params_mirror_payload(self) -> None:
        m = self._msr(total=912, duplicate=12)
        f = DuplicateRateRule().evaluate(DATASET_ID, [m])[0]
        assert f.params["total_rows"] == 912
        assert f.params["duplicate_rows"] == 12
        assert abs(float(f.params["duplicate_rate"]) - 12 / 912) < _TOL  # type: ignore[arg-type]

    def test_params_contains_threshold(self) -> None:
        m = self._msr(total=100, duplicate=2)
        f = DuplicateRateRule().evaluate(DATASET_ID, [m])[0]
        assert "warn_threshold" in f.params

    def test_statement_numbers_traceable_to_params(self) -> None:
        m = self._msr(total=912, duplicate=12)
        f = DuplicateRateRule().evaluate(DATASET_ID, [m])[0]
        _assert_statement_numbers_in_params(f.statement, f.params)


# ── DistributionShapeRule — Shapiro-Wilk path ─────────────────────────────────


class TestDistributionShapeSWFidelity:
    def _msr(self, *, w: float, n: int) -> Measurement:
        return Measurement.create(
            dataset_id=DATASET_ID,
            type="core.stats.normality",
            scope=_col("age"),
            payload={
                "test": "shapiro_wilk",
                "statistic": w,
                "p_value": 0.05,
                "sample_size": n,
            },
            provenance=_prov(),
        )

    def test_params_mirror_payload_ok(self) -> None:
        m = self._msr(w=0.980, n=500)
        f = DistributionShapeRule().evaluate(DATASET_ID, [m])[0]
        assert abs(float(f.params["statistic_w"]) - 0.980) < _TOL  # type: ignore[arg-type]
        assert f.params["sample_size"] == 500

    def test_params_mirror_payload_fail(self) -> None:
        m = self._msr(w=0.85, n=200)
        f = DistributionShapeRule().evaluate(DATASET_ID, [m])[0]
        assert abs(float(f.params["statistic_w"]) - 0.85) < _TOL  # type: ignore[arg-type]
        assert f.params["sample_size"] == 200

    def test_params_contains_thresholds(self) -> None:
        m = self._msr(w=0.97, n=100)
        f = DistributionShapeRule().evaluate(DATASET_ID, [m])[0]
        assert "threshold_ok" in f.params
        assert "threshold_warn" in f.params

    def test_statement_numbers_traceable_ok(self) -> None:
        m = self._msr(w=0.980, n=500)
        f = DistributionShapeRule().evaluate(DATASET_ID, [m])[0]
        _assert_statement_numbers_in_params(f.statement, f.params)

    def test_statement_numbers_traceable_fail(self) -> None:
        m = self._msr(w=0.85, n=200)
        f = DistributionShapeRule().evaluate(DATASET_ID, [m])[0]
        _assert_statement_numbers_in_params(f.statement, f.params)


# ── DistributionShapeRule — D'Agostino path ───────────────────────────────────


class TestDistributionShapeDAFidelity:
    def _norm_msr(self, *, n: int) -> Measurement:
        return Measurement.create(
            dataset_id=DATASET_ID,
            type="core.stats.normality",
            scope=_col("income"),
            payload={
                "test": "dagostino_pearson",
                "statistic": 10.5,
                "p_value": 0.001,
                "sample_size": n,
            },
            provenance=_prov(),
        )

    def _desc_msr(self, *, skewness: float, kurtosis: float, n: int) -> Measurement:
        return Measurement.create(
            dataset_id=DATASET_ID,
            type="core.stats.descriptive",
            scope=_col("income"),
            payload={
                "count": n,
                "mean": 5000.0,
                "std": 1000.0,
                "min": 1000.0,
                "max": 20000.0,
                "q25": 3000.0,
                "q50": 5000.0,
                "q75": 7000.0,
                "skewness": skewness,
                "excess_kurtosis": kurtosis,
            },
            provenance=_prov(),
        )

    def test_params_mirror_payload(self) -> None:
        nm = self._norm_msr(n=6000)
        dm = self._desc_msr(skewness=0.3, kurtosis=0.5, n=6000)
        f = DistributionShapeRule().evaluate(DATASET_ID, [nm, dm])[0]
        assert abs(float(f.params["skewness"]) - 0.3) < _TOL  # type: ignore[arg-type]
        assert abs(float(f.params["excess_kurtosis"]) - 0.5) < _TOL  # type: ignore[arg-type]
        assert f.params["sample_size"] == 6000

    def test_statement_numbers_traceable(self) -> None:
        nm = self._norm_msr(n=6000)
        dm = self._desc_msr(skewness=0.3, kurtosis=0.5, n=6000)
        f = DistributionShapeRule().evaluate(DATASET_ID, [nm, dm])[0]
        _assert_statement_numbers_in_params(f.statement, f.params)


# ── VariableAssociationRule ───────────────────────────────────────────────────


class TestVariableAssociationFidelity:
    def _msr(self, *, r: float, n: int) -> Measurement:
        return Measurement.create(
            dataset_id=DATASET_ID,
            type="core.stats.correlation",
            scope=_pair("hours", "productivity"),
            payload={
                "method": "pearson",
                "coefficient": r,
                "p_value": 0.001,
                "sample_size": n,
            },
            provenance=_prov(),
        )

    def test_params_mirror_payload(self) -> None:
        m = self._msr(r=0.456, n=890)
        fnds = VariableAssociationRule().evaluate(DATASET_ID, [m])
        assert fnds
        f = fnds[0]
        assert abs(float(f.params["coefficient"]) - 0.456) < _TOL  # type: ignore[arg-type]
        assert f.params["sample_size"] == 890

    def test_params_contains_thresholds(self) -> None:
        m = self._msr(r=0.5, n=100)
        f = VariableAssociationRule().evaluate(DATASET_ID, [m])[0]
        assert "emit_threshold" in f.params
        assert "fail_threshold" in f.params

    def test_statement_numbers_traceable_warn(self) -> None:
        m = self._msr(r=0.456, n=890)
        f = VariableAssociationRule().evaluate(DATASET_ID, [m])[0]
        _assert_statement_numbers_in_params(f.statement, f.params)

    def test_statement_numbers_traceable_fail(self) -> None:
        m = self._msr(r=0.75, n=500)
        f = VariableAssociationRule().evaluate(DATASET_ID, [m])[0]
        _assert_statement_numbers_in_params(f.statement, f.params)

    def test_below_emit_threshold_produces_no_finding(self) -> None:
        m = self._msr(r=0.2, n=500)
        assert VariableAssociationRule().evaluate(DATASET_ID, [m]) == []


# ── CategoryBalanceRule ───────────────────────────────────────────────────────


class TestCategoryBalanceFidelity:
    def _freq_msr(self, col: str, *, freqs: list[tuple[object, int]]) -> Measurement:
        total = sum(c for _, c in freqs)
        return Measurement.create(
            dataset_id=DATASET_ID,
            type="core.stats.frequency",
            scope=_col(col),
            payload={
                "total_count": total,
                "frequencies": [
                    {
                        "value": v,
                        "count": c,
                        "proportion": c / total if total else 0.0,
                    }
                    for v, c in sorted(freqs, key=lambda x: x[1], reverse=True)
                ],
            },
            provenance=_prov(),
        )

    def _uniq_msr(self, col: str, *, total: int, unique: int) -> Measurement:
        return Measurement.create(
            dataset_id=DATASET_ID,
            type="core.quality.uniqueness",
            scope=_col(col),
            payload={
                "total_count": total,
                "unique_count": unique,
                "duplicate_count": total - unique,
                "unique_proportion": unique / total if total else 0.0,
            },
            provenance=_prov(),
        )

    def test_params_mirror_payload(self) -> None:
        fm = self._freq_msr("sector", freqs=[("A", 700), ("B", 212)])
        um = self._uniq_msr("sector", total=912, unique=2)
        fnds = CategoryBalanceRule().evaluate(DATASET_ID, [fm, um])
        assert fnds
        f = fnds[0]
        assert abs(float(f.params["top_proportion"]) - 700 / 912) < 0.001  # type: ignore[arg-type]
        assert f.params["n_classes"] == 2

    def test_params_contains_thresholds(self) -> None:
        fm = self._freq_msr("sector", freqs=[("A", 800), ("B", 100)])
        um = self._uniq_msr("sector", total=900, unique=2)
        f = CategoryBalanceRule().evaluate(DATASET_ID, [fm, um])[0]
        assert "warn_threshold" in f.params
        assert "fail_threshold" in f.params

    def test_statement_numbers_traceable(self) -> None:
        fm = self._freq_msr("sector", freqs=[("A", 700), ("B", 212)])
        um = self._uniq_msr("sector", total=912, unique=2)
        f = CategoryBalanceRule().evaluate(DATASET_ID, [fm, um])[0]
        _assert_statement_numbers_in_params(f.statement, f.params)

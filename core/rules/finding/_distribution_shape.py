"""Finding rule: distribution shape (normality).

Uses effect-size statistics rather than p-values to avoid the large-sample
inflation problem (see docs/DECISIONS.md).

Shapiro-Wilk path  (sample_size <= 5000): uses W statistic.
D'Agostino path    (sample_size >  5000): uses skewness and excess_kurtosis
  from core.stats.descriptive.  If those fields are absent the rule returns
  no Finding for that column rather than guessing.

Threshold sources (all documented in docs/DECISIONS.md):
  SW_OK / SW_WARN         — practical convention, no strong theoretical basis.
  SKEW_OK / SKEW_WARN     — Bulmer (1979) "Principles of Statistics", heuristic.
  KURT_OK / KURT_WARN     — Hair et al. "Multivariate Data Analysis", heuristic.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from core.model import Finding, Measurement, Scope, Severity

# ── Shapiro-Wilk thresholds ───────────────────────────────────────────────────
# Convention, no single authoritative derivation.
# W >= 0.95 is widely used in applied-statistics guides as "acceptable".
_SW_OK: Final[float] = 0.95
_SW_WARN: Final[float] = 0.90

# ── D'Agostino thresholds (skewness) ─────────────────────────────────────────
# Bulmer (1979): |skew| < 0.5 = "fairly symmetric",
#                0.5-1.0 = "moderately skewed", >= 1.0 = "highly skewed".
# Widely cited in Hair et al.; citable heuristic, not a theorem.
_SKEW_OK: Final[float] = 0.5
_SKEW_WARN: Final[float] = 1.0

# ── D'Agostino thresholds (excess kurtosis) ──────────────────────────────────
# Hair et al. "Multivariate Data Analysis" practical heuristic.
# No theoretical derivation; commonly used in SEM/CFA contexts.
_KURT_OK: Final[float] = 1.0
_KURT_WARN: Final[float] = 2.0


class DistributionShapeRule:
    rule: str = "core.finding.distribution_shape"
    rule_version: str = "1.0.0"

    def evaluate(
        self, dataset_id: str, measurements: Sequence[Measurement]
    ) -> list[Finding]:
        normality = {
            m.scope: m for m in measurements if m.type == "core.stats.normality"
        }
        descriptive = {
            m.scope: m for m in measurements if m.type == "core.stats.descriptive"
        }
        results: list[Finding] = []
        for scope, norm_m in normality.items():
            finding = self._evaluate_column(
                dataset_id, scope, norm_m, descriptive.get(scope)
            )
            if finding is not None:
                results.append(finding)
        return results

    def _evaluate_column(
        self,
        dataset_id: str,
        scope: Scope,
        norm_m: Measurement,
        desc_m: Measurement | None,
    ) -> Finding | None:
        test = str(norm_m.payload["test"])
        n = int(norm_m.payload["sample_size"])  # type: ignore[call-overload]
        if test == "shapiro_wilk":
            return self._from_shapiro(dataset_id, scope, norm_m, n)
        if test == "dagostino_pearson":
            return self._from_dagostino(dataset_id, scope, norm_m, desc_m, n)
        return None

    def _from_shapiro(
        self,
        dataset_id: str,
        scope: Scope,
        norm_m: Measurement,
        n: int,
    ) -> Finding:
        w = float(norm_m.payload["statistic"])  # type: ignore[arg-type]
        if w >= _SW_OK:
            severity = Severity.OK
            statement = (
                f"Distribuição aproximadamente normal "
                f"(Shapiro-Wilk W={w:.4f} ≥ {_SW_OK}, n={n})."
            )
        elif w >= _SW_WARN:
            severity = Severity.WARN
            statement = (
                f"Desvio leve da normalidade "
                f"(Shapiro-Wilk W={w:.4f}, limiar ok={_SW_OK}, n={n})."
            )
        else:
            severity = Severity.FAIL
            statement = (
                f"Distribuição não normal "
                f"(Shapiro-Wilk W={w:.4f} < {_SW_WARN}, n={n})."
            )
        params: dict[str, object] = {
            "test": "shapiro_wilk",
            "statistic_w": w,
            "sample_size": n,
            "threshold_ok": _SW_OK,
            "threshold_warn": _SW_WARN,
        }
        return Finding.create(
            dataset_id=dataset_id,
            type="core.finding.distribution_shape",
            scope=scope,
            statement=statement,
            severity=severity,
            derived_from=(norm_m.id,),
            rule=self.rule,
            rule_version=self.rule_version,
            params=params,
        )

    def _from_dagostino(
        self,
        dataset_id: str,
        scope: Scope,
        norm_m: Measurement,
        desc_m: Measurement | None,
        n: int,
    ) -> Finding | None:
        if desc_m is None:
            return None
        raw_skew = desc_m.payload.get("skewness")
        raw_kurt = desc_m.payload.get("excess_kurtosis")
        if raw_skew is None or raw_kurt is None:
            return None

        skewness = float(raw_skew)  # type: ignore[arg-type]
        excess_kurtosis = float(raw_kurt)  # type: ignore[arg-type]
        abs_skew = abs(skewness)
        abs_kurt = abs(excess_kurtosis)

        sk_s = f"{skewness:.3f}"
        ku_s = f"{excess_kurtosis:.3f}"
        if abs_skew <= _SKEW_OK and abs_kurt <= _KURT_OK:
            severity = Severity.OK
            statement = (
                f"Distribuição aproximadamente normal "
                f"(assimetria={sk_s}, curtose excessiva={ku_s}, n={n})."
            )
        elif abs_skew <= _SKEW_WARN and abs_kurt <= _KURT_WARN:
            severity = Severity.WARN
            statement = (
                f"Desvio moderado da normalidade "
                f"(assimetria={sk_s}, curtose excessiva={ku_s}, n={n})."
            )
        else:
            severity = Severity.FAIL
            statement = (
                f"Distribuição não normal "
                f"(assimetria={sk_s}, curtose excessiva={ku_s}, n={n})."
            )
        params: dict[str, object] = {
            "test": "dagostino_pearson",
            "skewness": skewness,
            "excess_kurtosis": excess_kurtosis,
            "sample_size": n,
            "skewness_threshold_ok": _SKEW_OK,
            "skewness_threshold_warn": _SKEW_WARN,
            "excess_kurtosis_threshold_ok": _KURT_OK,
            "excess_kurtosis_threshold_warn": _KURT_WARN,
        }
        return Finding.create(
            dataset_id=dataset_id,
            type="core.finding.distribution_shape",
            scope=scope,
            statement=statement,
            severity=severity,
            derived_from=(norm_m.id, desc_m.id),
            rule=self.rule,
            rule_version=self.rule_version,
            params=params,
        )

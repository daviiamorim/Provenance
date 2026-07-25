"""Finding rule: category balance.

Applies only to columns that appear categorical, identified heuristically by:
  unique_proportion <= 0.05  OR  unique_count <= 20

Criterion: proportion of the most frequent non-null value (top_proportion).
Threshold source: practical convention, no theoretical derivation.
  0.60 warn — one class covers 60%+ of records, moderate imbalance signal.
  0.80 fail — one class covers 80%+ of records (~4:1 ratio), severe imbalance
              that degrades most classifiers without explicit resampling.
Documented in docs/DECISIONS.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from core.model import Finding, Measurement, Scope, Severity

_CATEGORICAL_UNIQUE_RATE: Final[float] = 0.05
_CATEGORICAL_UNIQUE_COUNT: Final[int] = 20
_WARN_THRESHOLD: Final[float] = 0.60
_FAIL_THRESHOLD: Final[float] = 0.80


class CategoryBalanceRule:
    rule: str = "core.finding.category_balance"
    rule_version: str = "1.0.0"

    def evaluate(
        self, dataset_id: str, measurements: Sequence[Measurement]
    ) -> list[Finding]:
        freq_map = {
            m.scope: m for m in measurements if m.type == "core.stats.frequency"
        }
        uniq_map = {
            m.scope: m for m in measurements if m.type == "core.quality.uniqueness"
        }
        results: list[Finding] = []
        for scope, freq_m in freq_map.items():
            uniq_m = uniq_map.get(scope)
            if uniq_m is None:
                continue
            finding = self._evaluate_column(dataset_id, scope, freq_m, uniq_m)
            if finding is not None:
                results.append(finding)
        return results

    def _evaluate_column(
        self,
        dataset_id: str,
        scope: Scope,
        freq_m: Measurement,
        uniq_m: Measurement,
    ) -> Finding | None:
        unique_rate = float(uniq_m.payload["unique_proportion"])  # type: ignore[arg-type]
        unique_count = int(uniq_m.payload["unique_count"])  # type: ignore[call-overload]

        is_categorical = (
            unique_rate <= _CATEGORICAL_UNIQUE_RATE
            or unique_count <= _CATEGORICAL_UNIQUE_COUNT
        )
        if not is_categorical:
            return None

        frequencies: list[dict[str, object]] = list(
            freq_m.payload.get("frequencies") or []  # type: ignore[call-overload]
        )
        if not frequencies:
            return None

        top_proportion = float(frequencies[0]["proportion"])  # type: ignore[arg-type]
        top_value = frequencies[0]["value"]
        n_classes = len(frequencies)

        if n_classes == 1:
            severity = Severity.FAIL
            statement = (
                f"Coluna degenerada — único valor distinto ({top_value!r}). "
                f"Regra: {self.rule}."
            )
        elif top_proportion > _FAIL_THRESHOLD:
            severity = Severity.FAIL
            statement = (
                f"Desequilíbrio severo: valor mais frequente ({top_value!r}) "
                f"representa {top_proportion:.1%} dos registros "
                f"(limiar fail={_FAIL_THRESHOLD:.0%}, {n_classes} classes)."
            )
        elif top_proportion > _WARN_THRESHOLD:
            severity = Severity.WARN
            statement = (
                f"Desequilíbrio moderado: valor mais frequente ({top_value!r}) "
                f"representa {top_proportion:.1%} dos registros "
                f"(limiar warn={_WARN_THRESHOLD:.0%}, {n_classes} classes)."
            )
        else:
            severity = Severity.OK
            statement = (
                f"Categorias balanceadas: valor mais frequente ({top_value!r}) "
                f"representa {top_proportion:.1%} dos registros ({n_classes} classes)."
            )

        params: dict[str, object] = {
            "top_proportion": top_proportion,
            "n_classes": n_classes,
            "warn_threshold": _WARN_THRESHOLD,
            "fail_threshold": _FAIL_THRESHOLD,
            "categorical_unique_rate_cutoff": _CATEGORICAL_UNIQUE_RATE,
            "categorical_unique_count_cutoff": _CATEGORICAL_UNIQUE_COUNT,
        }
        return Finding.create(
            dataset_id=dataset_id,
            type="core.finding.category_balance",
            scope=scope,
            statement=statement,
            severity=severity,
            derived_from=(freq_m.id, uniq_m.id),
            rule=self.rule,
            rule_version=self.rule_version,
            params=params,
        )

"""Finding rule: duplicate rate.

Always emits (including ok), because the ok Finding is positive evidence
that the check passed — Assessment rules need this anchor.

Threshold source: practical convention, no theoretical derivation.
  1% warn — small number of duplicates may be expected (re-entries,
             aggregation artifacts); above this suggests a systematic issue.
Documented in docs/DECISIONS.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from core.model import Finding, Measurement, Severity

# 1% threshold: practical convention (see module docstring).
_WARN_THRESHOLD: Final[float] = 0.01


class DuplicateRateRule:
    rule: str = "core.finding.duplicate_rate"
    rule_version: str = "1.0.0"

    def evaluate(
        self, dataset_id: str, measurements: Sequence[Measurement]
    ) -> list[Finding]:
        return [
            self._evaluate_column(dataset_id, m)
            for m in measurements
            if m.type == "core.quality.uniqueness"
        ]

    def _evaluate_column(self, dataset_id: str, m: Measurement) -> Finding:
        total = int(m.payload["total_count"])  # type: ignore[call-overload]
        duplicates = int(m.payload["duplicate_count"])  # type: ignore[call-overload]
        rate = duplicates / total if total > 0 else 0.0

        if duplicates == 0:
            severity = Severity.OK
            statement = f"Sem valores duplicados (0/{total})."
        elif rate <= _WARN_THRESHOLD:
            severity = Severity.WARN
            statement = (
                f"Taxa de duplicação baixa ({rate:.2%}, {duplicates}/{total}, "
                f"limiar={_WARN_THRESHOLD:.0%})."
            )
        else:
            severity = Severity.FAIL
            statement = (
                f"Taxa de duplicação elevada ({rate:.2%}, {duplicates}/{total}, "
                f"limiar={_WARN_THRESHOLD:.0%})."
            )
        params: dict[str, object] = {
            "duplicate_count": duplicates,
            "total_count": total,
            "duplicate_rate": rate,
            "warn_threshold": _WARN_THRESHOLD,
        }
        return Finding.create(
            dataset_id=dataset_id,
            type="core.finding.duplicate_rate",
            scope=m.scope,
            statement=statement,
            severity=severity,
            derived_from=(m.id,),
            rule=self.rule,
            rule_version=self.rule_version,
            params=params,
        )

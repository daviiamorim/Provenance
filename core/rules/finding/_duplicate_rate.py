"""Finding rule: duplicate rate (row-level).

Consumes core.quality.row_dedup (scope=DATASET). Emits one Finding per dataset.

A duplicate row is a row whose combination of all column values has already
appeared in the dataset.  This is categorically different from column-level value
repetition, which is a normal property of categorical columns.

Always emits (including ok), because the ok Finding is positive evidence that
the check passed — Assessment rules need this anchor.

Threshold source: practical convention, no theoretical derivation.
  1% warn — small number of duplicate rows may be expected (re-entries,
             aggregation artifacts); above this suggests a systematic issue.
Documented in docs/DECISIONS.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from core.model import Finding, Measurement, Scope, ScopeKind, Severity

# 1% threshold: practical convention (see module docstring).
_WARN_THRESHOLD: Final[float] = 0.01


class DuplicateRateRule:
    rule: str = "core.finding.duplicate_rate"
    rule_version: str = "1.0.0"

    def evaluate(
        self, dataset_id: str, measurements: Sequence[Measurement]
    ) -> list[Finding]:
        results: list[Finding] = []
        for m in measurements:
            if m.type != "core.quality.row_dedup":
                continue
            if m.scope.kind != ScopeKind.DATASET:
                continue
            results.append(self._evaluate_dataset(dataset_id, m))
        return results

    def _evaluate_dataset(self, dataset_id: str, m: Measurement) -> Finding:
        total = int(m.payload["total_rows"])  # type: ignore[call-overload]
        duplicate = int(m.payload["duplicate_rows"])  # type: ignore[call-overload]
        rate = float(m.payload["duplicate_proportion"])  # type: ignore[arg-type]

        if duplicate == 0:
            severity = Severity.OK
            statement = f"Sem linhas duplicadas (0/{total})."
        elif rate <= _WARN_THRESHOLD:
            severity = Severity.WARN
            statement = (
                f"Taxa de duplicação baixa ({rate:.2%}, {duplicate}/{total} linhas, "
                f"limiar={_WARN_THRESHOLD:.0%})."
            )
        else:
            severity = Severity.FAIL
            statement = (
                f"Taxa de duplicação elevada ({rate:.2%}, {duplicate}/{total} linhas, "
                f"limiar={_WARN_THRESHOLD:.0%})."
            )

        scope = Scope(kind=ScopeKind.DATASET, refs=(dataset_id,))
        params: dict[str, object] = {
            "duplicate_rows": duplicate,
            "total_rows": total,
            "duplicate_rate": rate,
            "warn_threshold": _WARN_THRESHOLD,
        }
        return Finding.create(
            dataset_id=dataset_id,
            type="core.finding.duplicate_rate",
            scope=scope,
            statement=statement,
            severity=severity,
            derived_from=(m.id,),
            rule=self.rule,
            rule_version=self.rule_version,
            params=params,
        )

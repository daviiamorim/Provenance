"""Finding rule: missing rate.

Threshold source: practical convention, commonly used in imputation literature
(van Buuren "Flexible Imputation of Missing Data" uses 5% as a common
decision point). No universal standard — documented as adjustable in
docs/DECISIONS.md.

Limitation: this rule reflects the missing rate as computed by the plugin
with the configured null_sentinels. It cannot validate whether the sentinel
list is appropriate for the column's domain. The applied sentinels are
recorded in params so the evidence chain makes the assumption explicit.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from core.model import Finding, Measurement, Severity

# 5% threshold: practical convention (see module docstring).
_WARN_THRESHOLD: Final[float] = 0.05


class MissingRateRule:
    rule: str = "core.finding.missing_rate"
    rule_version: str = "1.0.0"

    def evaluate(
        self, dataset_id: str, measurements: Sequence[Measurement]
    ) -> list[Finding]:
        return [
            self._evaluate_column(dataset_id, m)
            for m in measurements
            if m.type == "core.quality.missing"
        ]

    def _evaluate_column(self, dataset_id: str, m: Measurement) -> Finding:
        rate = float(m.payload["missing_proportion"])  # type: ignore[arg-type]
        total = int(m.payload["total_count"])  # type: ignore[call-overload]
        missing = int(m.payload["missing_count"])  # type: ignore[call-overload]
        sentinels: list[object] = list(
            m.provenance.params.get("null_sentinels") or []  # type: ignore[call-overload]
        )

        if rate == 0.0:
            severity = Severity.OK
            statement = f"Sem valores ausentes ({missing}/{total})."
        elif rate <= _WARN_THRESHOLD:
            severity = Severity.WARN
            statement = (
                f"Taxa de ausência baixa ({rate:.1%}, {missing}/{total}, "
                f"limiar={_WARN_THRESHOLD:.0%})."
            )
        else:
            severity = Severity.FAIL
            statement = (
                f"Taxa de ausência elevada ({rate:.1%}, {missing}/{total}, "
                f"limiar={_WARN_THRESHOLD:.0%})."
            )
        if sentinels:
            statement += f" Sentinelas aplicadas: {sentinels}."

        params: dict[str, object] = {
            "missing_proportion": rate,
            "total_count": total,
            "missing_count": missing,
            "warn_threshold": _WARN_THRESHOLD,
            "null_sentinels_applied": sentinels,
        }
        return Finding.create(
            dataset_id=dataset_id,
            type="core.finding.missing_rate",
            scope=m.scope,
            statement=statement,
            severity=severity,
            derived_from=(m.id,),
            rule=self.rule,
            rule_version=self.rule_version,
            params=params,
        )

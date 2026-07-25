"""Finding rule: variable association (pairwise correlation).

Does NOT emit for |r| < 0.3 — weak associations are not actionable and
emitting them would create noise.  No Finding for a pair means weak/no
association; Assessment rules interpret the absence accordingly.

Uses |coefficient| (effect size), never p_value, as the severity criterion.
p_value is N-dependent and becomes misleading for large samples (see
docs/DECISIONS.md for the general principle).

Threshold source: Cohen (1988) "Statistical Power Analysis for the
Behavioral Sciences", 2nd ed.  Small=0.1, medium=0.3, large=0.5.
We use 0.3 as the emit floor (medium effect) and 0.7 as the fail
threshold (strong/very strong effect → multicollinearity concern).
The 0.7 fail threshold is an extension beyond Cohen's categories;
it is a practical convention documented in docs/DECISIONS.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from core.model import Finding, Measurement, Severity

_EMIT_THRESHOLD: Final[float] = 0.3  # Cohen (1988): medium effect floor
_FAIL_THRESHOLD: Final[float] = 0.7  # practical convention, multicollinearity concern


class VariableAssociationRule:
    rule: str = "core.finding.variable_association"
    rule_version: str = "1.0.0"

    def evaluate(
        self, dataset_id: str, measurements: Sequence[Measurement]
    ) -> list[Finding]:
        results: list[Finding] = []
        for m in measurements:
            if m.type != "core.stats.correlation":
                continue
            finding = self._evaluate_pair(dataset_id, m)
            if finding is not None:
                results.append(finding)
        return results

    def _evaluate_pair(self, dataset_id: str, m: Measurement) -> Finding | None:
        r = float(m.payload["coefficient"])  # type: ignore[arg-type]
        method = str(m.payload["method"])
        n = int(m.payload["sample_size"])  # type: ignore[call-overload]
        abs_r = abs(r)

        if abs_r < _EMIT_THRESHOLD:
            return None

        direction = "positiva" if r >= 0 else "negativa"
        if abs_r >= _FAIL_THRESHOLD:
            severity = Severity.FAIL
            statement = (
                f"Associação forte {direction} ({method}: r={r:.3f}, n={n}). "
                f"Risco de multicolinearidade (|r| ≥ {_FAIL_THRESHOLD})."
            )
        else:
            severity = Severity.WARN
            statement = (
                f"Associação moderada {direction} ({method}: r={r:.3f}, n={n}) "
                f"(|r| ≥ {_EMIT_THRESHOLD})."
            )
        params: dict[str, object] = {
            "coefficient": r,
            "method": method,
            "sample_size": n,
            "emit_threshold": _EMIT_THRESHOLD,
            "fail_threshold": _FAIL_THRESHOLD,
        }
        return Finding.create(
            dataset_id=dataset_id,
            type="core.finding.variable_association",
            scope=m.scope,
            statement=statement,
            severity=severity,
            derived_from=(m.id,),
            rule=self.rule,
            rule_version=self.rule_version,
            params=params,
        )

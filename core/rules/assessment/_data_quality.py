"""Assessment rule: data_quality.

Answers: "Is this dataset ready from a data quality standpoint?"

Composed from: missing_rate and duplicate_rate only.

Intentionally excludes: distribution_shape (non-normality ≠ defect),
variable_association (correlation is a feature, not a quality issue),
category_balance (imbalance ≠ bad quality — a naturally imbalanced dataset
can be perfectly high quality).

That exclusion is the concrete illustration from the spec: the same
category_balance Finding that makes modeling_readiness fail leaves
data_quality unaffected.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from core.model import Assessment, Finding, Scope, ScopeKind, Severity

_CONSIDERED: Final[frozenset[str]] = frozenset(
    {
        "core.finding.missing_rate",
        "core.finding.duplicate_rate",
    }
)

_POLICY: dict[str, object] = {
    "considered_finding_types": sorted(_CONSIDERED),
    "verdict_ok": "acceptable",
    "verdict_warn": "marginal",
    "verdict_fail": "unacceptable",
}

GOAL: Final[str] = "data_quality"


class DataQualityRule:
    rule: str = "core.assessment.data_quality"
    rule_version: str = "1.0.0"

    def evaluate(
        self, dataset_id: str, goal: str, findings: Sequence[Finding]
    ) -> Assessment | None:
        if goal != GOAL:
            return None

        relevant = [f for f in findings if f.type in _CONSIDERED]
        if not relevant:
            return None

        fail_findings = [f for f in relevant if f.severity == Severity.FAIL]
        warn_findings = [f for f in relevant if f.severity == Severity.WARN]

        if fail_findings:
            severity = Severity.FAIL
            verdict = "unacceptable"
        elif warn_findings:
            severity = Severity.WARN
            verdict = "marginal"
        else:
            severity = Severity.OK
            verdict = "acceptable"

        scope = Scope(kind=ScopeKind.DATASET, refs=(dataset_id,))
        return Assessment.create(
            dataset_id=dataset_id,
            type="core.assessment.data_quality",
            scope=scope,
            goal=goal,
            verdict=verdict,
            severity=severity,
            derived_from=tuple(f.id for f in relevant),
            rule=self.rule,
            rule_version=self.rule_version,
            policy=_POLICY,
        )

"""Assessment rule: modeling_readiness.

Answers: "Is this dataset suitable for supervised machine learning?"

Composed from: missing_rate, category_balance, variable_association (fail/warn
triggers), and distribution_shape (warn trigger only — non-normality may
require transformation but does not block training by itself).

The key asymmetry vs data_quality: category_balance fail → modeling_readiness
fail, but the same Finding leaves data_quality unaffected (imbalance is a
characteristic, not a defect).  That distinction is what justifies two
separate Assessment goals.

Policy is stored on the Assessment for auditability — changing which Finding
types trigger fail/warn must bump rule_version.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from core.model import Assessment, Finding, Scope, ScopeKind, Severity

_FAIL_TYPES: Final[frozenset[str]] = frozenset({
    "core.finding.missing_rate",
    "core.finding.category_balance",
    "core.finding.variable_association",
})
_WARN_TYPES: Final[frozenset[str]] = frozenset({
    "core.finding.distribution_shape",
})
_ALL_CONSIDERED: Final[frozenset[str]] = _FAIL_TYPES | _WARN_TYPES

_POLICY: dict[str, object] = {
    "fail_on_finding_types": sorted(_FAIL_TYPES),
    "warn_on_finding_types": sorted(_WARN_TYPES),
    "verdict_ok": "eligible",
    "verdict_warn": "needs_attention",
    "verdict_fail": "not_eligible",
}

GOAL: Final[str] = "modeling_readiness"


class ModelingReadinessRule:
    rule: str = "core.assessment.modeling_readiness"
    rule_version: str = "1.0.0"

    def evaluate(
        self, dataset_id: str, goal: str, findings: Sequence[Finding]
    ) -> Assessment | None:
        if goal != GOAL:
            return None

        relevant = [f for f in findings if f.type in _ALL_CONSIDERED]
        if not relevant:
            return None

        fail_findings = [
            f for f in relevant
            if f.type in _FAIL_TYPES and f.severity == Severity.FAIL
        ]
        warn_findings = [
            f for f in relevant
            if (f.type in _FAIL_TYPES and f.severity == Severity.WARN)
            or (f.type in _WARN_TYPES and f.severity in {Severity.FAIL, Severity.WARN})
        ]

        if fail_findings:
            severity = Severity.FAIL
            verdict = "not_eligible"
        elif warn_findings:
            severity = Severity.WARN
            verdict = "needs_attention"
        else:
            severity = Severity.OK
            verdict = "eligible"

        scope = Scope(kind=ScopeKind.DATASET, refs=(dataset_id,))
        return Assessment.create(
            dataset_id=dataset_id,
            type="core.assessment.modeling_readiness",
            scope=scope,
            goal=goal,
            verdict=verdict,
            severity=severity,
            derived_from=tuple(f.id for f in relevant),
            rule=self.rule,
            rule_version=self.rule_version,
            policy=_POLICY,
        )

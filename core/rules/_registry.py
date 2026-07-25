"""Rule registry — analogous to SchemaRegistry in core/model.py.

FindingRule and AssessmentRule are Protocols; rules are stateless objects
registered at module load time. The registry dispatches evaluate() calls
and aggregates results. No state, no I/O, no LLM calls inside rules.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from core.model import Assessment, Finding, Measurement


@runtime_checkable
class FindingRule(Protocol):
    """A versioned, pure function that derives Findings from Measurements.

    evaluate() receives ALL measurements for a dataset and filters internally.
    It may return zero or more Findings — returning [] is a valid result.
    Changing any threshold that affects the verdict must bump rule_version.
    """

    rule: str
    rule_version: str

    def evaluate(
        self, dataset_id: str, measurements: Sequence[Measurement]
    ) -> list[Finding]: ...


@runtime_checkable
class AssessmentRule(Protocol):
    """A versioned, pure function that derives one Assessment from Findings.

    evaluate() is called once per goal. It may return None (not applicable
    for this goal). Changing any threshold must bump rule_version.
    """

    rule: str
    rule_version: str

    def evaluate(
        self, dataset_id: str, goal: str, findings: Sequence[Finding]
    ) -> Assessment | None: ...


class RuleRegistry:
    """Registry of all Finding and Assessment rules.

    Rules are registered at import time (see core/rules/__init__.py).
    run_findings() and run_assessments() are the only entry points for
    the pipeline; they never mutate state.
    """

    def __init__(self) -> None:
        self._finding_rules: list[FindingRule] = []
        self._assessment_rules: list[AssessmentRule] = []

    def register_finding(self, rule: FindingRule) -> None:
        self._finding_rules.append(rule)

    def register_assessment(self, rule: AssessmentRule) -> None:
        self._assessment_rules.append(rule)

    def run_findings(
        self, dataset_id: str, measurements: Sequence[Measurement]
    ) -> list[Finding]:
        results: list[Finding] = []
        for rule in self._finding_rules:
            results.extend(rule.evaluate(dataset_id, measurements))
        return results

    def run_assessments(
        self, dataset_id: str, goal: str, findings: Sequence[Finding]
    ) -> list[Assessment]:
        results: list[Assessment] = []
        for rule in self._assessment_rules:
            assessment = rule.evaluate(dataset_id, goal, findings)
            if assessment is not None:
                results.append(assessment)
        return results

    def finding_rules(self) -> list[FindingRule]:
        return list(self._finding_rules)

    def assessment_rules(self) -> list[AssessmentRule]:
        return list(self._assessment_rules)


RULE_REGISTRY: RuleRegistry = RuleRegistry()

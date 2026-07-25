"""Validator — orchestrates the three layers for a single sentence.

Layers run in order: syntactic → numeric → semantic. Execution stops at the
first failure (cost escalates with each layer, so early stopping matters).

Returns all ValidationChecks that were actually run (not just the failing one),
so the caller can build a complete ValidationRecord for the Claim.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.llm import LanguageModel
from core.model import (
    Assessment,
    Finding,
    ValidationCheck,
    ValidationLayer,
    ValidationVerdict,
)
from core.validation._layer1 import CITATION_RE, check_syntactic
from core.validation._layer2 import check_numeric
from core.validation._layer3 import check_semantic


@dataclass(frozen=True)
class RejectionRecord:
    """Structured record of a rejected sentence.

    This is product-visible state, not internal logging. It will be exposed
    in the API and shown in the validation panel of the frontend.
    """

    text: str
    layer: ValidationLayer
    reason_code: str
    detail: dict[str, object]
    attempt: int


@dataclass(frozen=True)
class ValidationMetrics:
    total_sentences: int
    rejected_layer1: int
    rejected_layer2: int
    rejected_layer3: int
    discarded: int

    @property
    def rejection_rate_by_layer(self) -> dict[str, float]:
        denom = max(self.total_sentences, 1)
        return {
            "syntactic": self.rejected_layer1 / denom,
            "numeric": self.rejected_layer2 / denom,
            "semantic": self.rejected_layer3 / denom,
        }

    @property
    def discard_rate(self) -> float:
        return self.discarded / max(self.total_sentences, 1)


class Validator:
    """Validates a sentence through all three layers, stopping at first failure.

    Inject a LanguageModel for the semantic judge. The same or a different
    instance may be used for composing — the Validator does not care.
    """

    def __init__(
        self,
        judge: LanguageModel,
        tolerance: float = 0.005,
    ) -> None:
        self._judge = judge
        self._tolerance = tolerance

    def validate(
        self,
        sentence: str,
        findings: Sequence[Finding],
        assessments: Sequence[Assessment],
    ) -> tuple[bool, list[ValidationCheck]]:
        """Validate one sentence. Returns (passed, checks_run).

        checks_run contains every ValidationCheck that executed — caller builds
        ValidationRecord from them. Stops after the first FAIL.
        """
        checks: list[ValidationCheck] = []
        valid_ids = frozenset([f.id for f in findings] + [a.id for a in assessments])

        c1 = check_syntactic(sentence, valid_ids)
        checks.append(c1)
        if c1.verdict == ValidationVerdict.FAIL:
            return False, checks

        cited_ids = set(CITATION_RE.findall(sentence))
        cited_findings = [f for f in findings if f.id in cited_ids]
        cited_assessments = [a for a in assessments if a.id in cited_ids]

        c2 = check_numeric(sentence, cited_findings, cited_assessments, self._tolerance)
        checks.append(c2)
        if c2.verdict == ValidationVerdict.FAIL:
            return False, checks

        c3 = check_semantic(sentence, cited_findings, cited_assessments, self._judge)
        checks.append(c3)
        return c3.verdict == ValidationVerdict.PASS, checks

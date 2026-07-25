"""Validation layer 1 — syntactic.

Cost: negligible (pure regex + set lookup).

Rejects a sentence when:
  - no citation is present (no [fnd-…] or [ast-…] bracket)
  - any cited ID is not in the known set for this run
"""

from __future__ import annotations

import re
import time

from core.model import ValidationCheck, ValidationLayer, ValidationVerdict

# Exported so _validator.py can reuse it for citation resolution.
CITATION_RE: re.Pattern[str] = re.compile(r"\[((?:fnd|ast)-[0-9a-f]+)\]")


def check_syntactic(
    sentence: str,
    valid_ids: frozenset[str],
) -> ValidationCheck:
    t0 = time.monotonic_ns()
    citations = CITATION_RE.findall(sentence)

    if not citations:
        return ValidationCheck(
            layer=ValidationLayer.SYNTACTIC,
            verdict=ValidationVerdict.FAIL,
            reason_code="no_citation",
            detail={"sentence_preview": sentence[:120]},
            duration_ms=int((time.monotonic_ns() - t0) / 1_000_000),
        )

    unknown = [c for c in citations if c not in valid_ids]
    if unknown:
        return ValidationCheck(
            layer=ValidationLayer.SYNTACTIC,
            verdict=ValidationVerdict.FAIL,
            reason_code="unknown_citation",
            detail={"unknown_ids": unknown},
            duration_ms=int((time.monotonic_ns() - t0) / 1_000_000),
        )

    return ValidationCheck(
        layer=ValidationLayer.SYNTACTIC,
        verdict=ValidationVerdict.PASS,
        reason_code="ok",
        detail={"citations": citations},
        duration_ms=int((time.monotonic_ns() - t0) / 1_000_000),
    )

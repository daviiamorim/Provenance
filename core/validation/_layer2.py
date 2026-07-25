"""Validation layer 2 — numeric.

Cost: deterministic, O(numbers x sources).

Extracts numbers from the claim sentence in Brazilian format (comma decimal
separator, period thousands separator). For each extracted number, verifies
it appears — within an absolute tolerance — in the numeric values of the
cited Findings' params and Assessments' policy.

Why params/policy and not Measurement payloads:
  Finding.params mirrors all Measurement-derived values that the rule
  embedded in the statement (e.g. missing_proportion, total_count). Opening
  a direct channel to Measurements would risk leaking raw data through the
  validation path. The fidelity guarantee (Finding numbers == Measurement
  numbers) is enforced by tests/test_statement_fidelity.py at rule-creation
  time, not here.

Percentage handling: a number followed by % has two candidate values for
comparison — the percentage itself (e.g. 7.6) AND the proportion (e.g. 0.076).
Either matching within tolerance is a pass.

Tolerance: absolute, configurable, default 0.005 (covers rounding to 2 d.p.).
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence

from core.model import (
    Assessment,
    Finding,
    ValidationCheck,
    ValidationLayer,
    ValidationVerdict,
)

# Brazilian format: "1.234,56" | "7,6" | "912" — period is thousands separator,
# comma is decimal separator.
_BR_NUM_RE: re.Pattern[str] = re.compile(
    r"(?<!\w)" r"(\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?)" r"(\s*%)?" r"(?!\w)"
)


def _parse_br(raw: str) -> float:
    """Parse Brazilian-format number string to float."""
    # Remove thousands separators (period only when \d{3} follows — already in regex)
    cleaned = re.sub(r"\.(?=\d{3})", "", raw)
    return float(cleaned.replace(",", "."))


def extract_br_numbers(text: str) -> list[tuple[float, bool]]:
    """Extract (value, is_percentage) pairs from text in Brazilian format.

    Exported so fidelity tests can reuse the same extractor.
    """
    results: list[tuple[float, bool]] = []
    for m in _BR_NUM_RE.finditer(text):
        try:
            value = _parse_br(m.group(1))
        except ValueError:
            continue
        is_pct = bool(m.group(2) and m.group(2).strip() == "%")
        results.append((value, is_pct))
    return results


def _collect_source_values(
    findings: Sequence[Finding],
    assessments: Sequence[Assessment],
) -> list[float]:
    """Collect all numeric values from Finding.params and Assessment.policy."""
    values: list[float] = []

    def _recurse(obj: object) -> None:
        if isinstance(obj, bool):
            return
        if isinstance(obj, (int, float)):
            values.append(float(obj))
        elif isinstance(obj, dict):
            for v in obj.values():
                _recurse(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _recurse(item)

    for f in findings:
        _recurse(dict(f.params))
    for a in assessments:
        _recurse(dict(a.policy))

    return values


def _is_supported(
    value: float,
    *,
    is_pct: bool,
    source_values: list[float],
    tolerance: float,
) -> bool:
    candidates = [value]
    if is_pct:
        candidates.append(value / 100.0)
    return any(abs(c - s) <= tolerance for c in candidates for s in source_values)


def check_numeric(
    sentence: str,
    cited_findings: Sequence[Finding],
    cited_assessments: Sequence[Assessment],
    tolerance: float = 0.005,
) -> ValidationCheck:
    t0 = time.monotonic_ns()
    extracted = extract_br_numbers(sentence)

    if not extracted:
        return ValidationCheck(
            layer=ValidationLayer.NUMERIC,
            verdict=ValidationVerdict.PASS,
            reason_code="no_numbers",
            detail={},
            duration_ms=int((time.monotonic_ns() - t0) / 1_000_000),
        )

    source_values = _collect_source_values(cited_findings, cited_assessments)
    unsupported: list[str] = []

    for value, is_pct in extracted:
        if not _is_supported(
            value, is_pct=is_pct, source_values=source_values, tolerance=tolerance
        ):
            label = f"{value}%" if is_pct else str(value)
            unsupported.append(label)

    if unsupported:
        return ValidationCheck(
            layer=ValidationLayer.NUMERIC,
            verdict=ValidationVerdict.FAIL,
            reason_code="unsupported_number",
            detail={
                "unsupported": unsupported,
                "tolerance": tolerance,
                "source_count": len(source_values),
            },
            duration_ms=int((time.monotonic_ns() - t0) / 1_000_000),
        )

    return ValidationCheck(
        layer=ValidationLayer.NUMERIC,
        verdict=ValidationVerdict.PASS,
        reason_code="ok",
        detail={"checked": len(extracted), "tolerance": tolerance},
        duration_ms=int((time.monotonic_ns() - t0) / 1_000_000),
    )

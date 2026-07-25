"""Validation layer 3 — semantic entailment.

Cost: one model call per sentence (most expensive layer).

The judge receives ONLY:
  - the isolated sentence under review
  - the serialized cited Findings/Assessments

It receives nothing else: no other sentences, no dataset, no Measurements,
no full report context. This isolation is load-bearing — a judge that sees
the full context can rationalize any sentence. The narrow context forces it
to check only what the sentence actually claims against only what it cites.

Verdict: entailed | unsupported | contradicted. Only entailed passes.
Any unparseable response is treated as unsupported (safe default).
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from core.llm import LanguageModel, SemanticVerdict
from core.model import (
    Assessment,
    Finding,
    ValidationCheck,
    ValidationLayer,
    ValidationVerdict,
)

_VERDICT_MAP: dict[str, SemanticVerdict] = {v.value: v for v in SemanticVerdict}


def _serialize_cited_sources(
    findings: Sequence[Finding],
    assessments: Sequence[Assessment],
) -> str:
    lines = [f"[{f.id}] {f.severity.value.upper()} — {f.statement}" for f in findings]
    lines.extend(
        f"[{a.id}] {a.severity.value.upper()} — goal={a.goal}, verdict={a.verdict}"
        for a in assessments
    )
    return "\n".join(lines)


def _build_judge_prompt(
    sentence: str,
    cited_findings: Sequence[Finding],
    cited_assessments: Sequence[Assessment],
) -> str:
    sources = _serialize_cited_sources(cited_findings, cited_assessments)
    return (
        "Você é um verificador de fatos. Classifique a AFIRMAÇÃO abaixo:\n"
        "  entailed     — claramente sustentada pelas FONTES\n"
        "  unsupported  — não sustentada pelas FONTES\n"
        "  contradicted — contradiz as FONTES\n\n"
        f'AFIRMAÇÃO: "{sentence}"\n\n'
        f"FONTES:\n{sources}\n\n"
        "Responda com exatamente uma palavra: entailed | unsupported | contradicted"
    )


def check_semantic(
    sentence: str,
    cited_findings: Sequence[Finding],
    cited_assessments: Sequence[Assessment],
    judge: LanguageModel,
) -> ValidationCheck:
    t0 = time.monotonic_ns()
    prompt = _build_judge_prompt(sentence, cited_findings, cited_assessments)
    raw = judge.complete(prompt).strip().lower()

    verdict = _VERDICT_MAP.get(raw, SemanticVerdict.UNSUPPORTED)
    if raw not in _VERDICT_MAP:
        raw = f"unparseable:{raw!r}"

    passed = verdict == SemanticVerdict.ENTAILED
    return ValidationCheck(
        layer=ValidationLayer.SEMANTIC,
        verdict=ValidationVerdict.PASS if passed else ValidationVerdict.FAIL,
        reason_code=verdict.value,
        detail={"raw_response": raw},
        duration_ms=int((time.monotonic_ns() - t0) / 1_000_000),
    )

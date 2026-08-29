"""Composer — generates a Claims report from Findings and Assessments.

ISOLATION CONTRACT (enforced by tests/test_composer.py):
  generate_report() accepts only Findings, Assessments, LanguageModel instances,
  run_id, dataset_id, and tolerance. It never accepts Dataset, Measurement, or
  Artifact. The signature is the enforcement mechanism — if those types appear
  in the parameter list, the isolation test fails at import time.

RETRY LOOP:
  Each sentence gets up to MAX_ATTEMPTS attempts (initial + rewrites).
  After MAX_ATTEMPTS failures the sentence is discarded and recorded.
  Only sentences that pass all three validation layers become Claims.

SERIALIZATION:
  _serialize_sources() accesses only:
    Finding.id, .statement, .severity, .scope, .params
    Assessment.id, .verdict, .severity, .goal, .policy
  None of these fields contain raw dataset values — they are either hashes,
  rule-derived text, or policy thresholds. This is why the Validator's numeric
  layer comparing against params/policy is sufficient without reaching through
  to Measurements.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from core.llm import LanguageModel
from core.model import (
    Assessment,
    Claim,
    Finding,
    ValidationRecord,
    ValidationStatus,
)
from core.validation._layer1 import CITATION_RE
from core.validation._validator import (
    RejectionRecord,
    ValidationMetrics,
    Validator,
)

_MAX_ATTEMPTS: int = 2

_SEV_LABEL: dict[str, str] = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}


# ── serialization ─────────────────────────────────────────────────────────────


def _serialize_sources(
    findings: Sequence[Finding],
    assessments: Sequence[Assessment],
) -> str:
    """Serialize Findings and Assessments for inclusion in an LLM prompt.

    Accesses only id, statement, severity, scope, params (Finding) and
    id, verdict, severity, goal, policy (Assessment). Never raw data.
    """
    lines: list[str] = []

    if findings:
        lines.append("## Findings\n")
        for f in findings:
            sev = _SEV_LABEL.get(str(f.severity), str(f.severity))
            scope_desc = f"{f.scope.kind.value} {list(f.scope.refs)}"
            lines.append(f"[{f.id}] ({scope_desc}) {sev}")
            lines.append(f.statement)
            lines.append("")

    if assessments:
        lines.append("## Assessments\n")
        for a in assessments:
            sev = _SEV_LABEL.get(str(a.severity), str(a.severity))
            lines.append(f"[{a.id}] (objetivo: {a.goal}) {sev} — {a.verdict}")
            lines.append("")

    return "\n".join(lines)


def _build_generation_prompt(
    findings: Sequence[Finding],
    assessments: Sequence[Assessment],
) -> str:
    sources = _serialize_sources(findings, assessments)
    return (
        "Você é um analista de dados. Com base EXCLUSIVAMENTE nas conclusões "
        "abaixo, escreva uma afirmação por conclusão relevante.\n\n"
        "FORMATO OBRIGATÓRIO (um bloco por afirmação, separados por linha em branco):\n"
        "AFIRMAÇÃO: <frase declarativa com pelo menos um ID citado, ex: [fnd-abc123]>\n"
        "EXPLICAÇÃO: <detalhamento em linguagem simples, sem citar IDs>\n\n"
        "REGRAS:\n"
        "1. Cada AFIRMAÇÃO deve conter pelo menos um ID entre colchetes.\n"
        "2. A EXPLICAÇÃO nunca contém IDs — só texto em português claro.\n"
        "3. Não introduza informações não sustentadas pelos IDs citados.\n\n"
        f"{sources}\n"
        "---"
    )


def _build_rewrite_prompt(
    sentence: str,
    reason_code: str,
    layer_name: str,
    detail: dict[str, object],
    sources_text: str,
    attempt: int,
) -> str:
    detail_str = ", ".join(f"{k}={v!r}" for k, v in detail.items())
    return (
        f"[Tentativa {attempt + 1}/{_MAX_ATTEMPTS}]\n\n"
        "A frase abaixo foi rejeitada pelo validador. "
        "Reescreva-a corrigindo o problema indicado.\n\n"
        f"PROBLEMA: [{layer_name}] {reason_code}: {detail_str}\n\n"
        f"FONTES:\n{sources_text}\n\n"
        f'FRASE REJEITADA: "{sentence}"\n\n'
        "Reescreva apenas a frase corrigida (sem explicação):"
    )


# ── pair parsing ─────────────────────────────────────────────────────────────


def _parse_claim_pairs(text: str) -> list[tuple[str, str]]:
    """Parse LLM output into (statement, explanation) pairs.

    Expects blocks separated by blank lines, each with AFIRMAÇÃO: and
    optionally EXPLICAÇÃO: lines. Blocks without AFIRMAÇÃO: are skipped.
    """
    pairs: list[tuple[str, str]] = []
    blocks = re.split(r"\n{2,}", text.strip())
    for block in blocks:
        stmt = ""
        expl = ""
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("AFIRMAÇÃO:"):
                stmt = stripped[len("AFIRMAÇÃO:") :].strip()
            elif stripped.startswith("EXPLICAÇÃO:"):
                expl = stripped[len("EXPLICAÇÃO:") :].strip()
        if stmt:
            if not stmt.endswith((".", "!", "?")):
                stmt += "."
            pairs.append((stmt, expl))
    return pairs


# ── result type ───────────────────────────────────────────────────────────────


@dataclass
class ReportResult:
    claims: list[Claim]
    rejected: list[RejectionRecord]
    metrics: ValidationMetrics


# ── main entry point ──────────────────────────────────────────────────────────


def generate_report(
    findings: Sequence[Finding],
    assessments: Sequence[Assessment],
    composer_model: LanguageModel,
    judge_model: LanguageModel,
    run_id: str,
    dataset_id: str,
    tolerance: float = 0.005,
) -> ReportResult:
    """Generate a Claims report from Findings and Assessments.

    ISOLATION: signature deliberately excludes Dataset, Measurement, Artifact.
    tests/test_composer.py verifies this with inspect.signature() at import time.
    """
    validator = Validator(judge=judge_model, tolerance=tolerance)
    sources_text = _serialize_sources(findings, assessments)
    generation_prompt = _build_generation_prompt(findings, assessments)

    raw_text = composer_model.complete(generation_prompt)
    pairs = _parse_claim_pairs(raw_text)

    claims: list[Claim] = []
    rejected_records: list[RejectionRecord] = []
    layer_counts: dict[str, int] = {
        "syntactic": 0,
        "numeric": 0,
        "semantic": 0,
    }
    discarded = 0

    for statement, explanation in pairs:
        current = statement

        for attempt in range(_MAX_ATTEMPTS):
            passed, checks = validator.validate(current, findings, assessments)

            if passed:
                cited_ids = tuple(sorted(set(CITATION_RE.findall(current))))
                record = ValidationRecord(
                    status=ValidationStatus.PASSED,
                    attempts=attempt + 1,
                    checks=tuple(checks),
                    final_layer_reached=checks[-1].layer.value,
                )
                claims.append(
                    Claim.create(
                        dataset_id=dataset_id,
                        run_id=run_id,
                        text=current,
                        explanation=explanation,
                        supports=cited_ids,
                        validation=record,
                    )
                )
                break

            # Rejection — rewrite targets only the statement; explanation is preserved
            failed = checks[-1]
            layer_counts[failed.layer.value] += 1
            rejected_records.append(
                RejectionRecord(
                    text=current,
                    layer=failed.layer,
                    reason_code=failed.reason_code,
                    detail=dict(failed.detail),
                    attempt=attempt + 1,
                )
            )

            if attempt + 1 < _MAX_ATTEMPTS:
                rewrite_prompt = _build_rewrite_prompt(
                    current,
                    failed.reason_code,
                    failed.layer.value,
                    dict(failed.detail),
                    sources_text,
                    attempt,
                )
                current = composer_model.complete(rewrite_prompt).strip()
                if not current.endswith((".", "!", "?")):
                    current += "."
            else:
                discarded += 1

    metrics = ValidationMetrics(
        total_sentences=len(pairs),
        rejected_layer1=layer_counts["syntactic"],
        rejected_layer2=layer_counts["numeric"],
        rejected_layer3=layer_counts["semantic"],
        discarded=discarded,
    )
    return ReportResult(claims=claims, rejected=rejected_records, metrics=metrics)

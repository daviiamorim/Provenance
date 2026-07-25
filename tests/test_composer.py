"""Tests for core.composer.

Key invariant: generate_report() must never accept Dataset, Measurement,
or Artifact — verified by signature inspection (structural enforcement, not
convention).
"""

from __future__ import annotations

import inspect

import pytest

from core.composer import ReportResult, _serialize_sources, generate_report
from core.llm import StubLanguageModel
from core.model import (
    Assessment,
    Claim,
    Finding,
    Measurement,
    Provenance,
    Scope,
    ScopeKind,
    Severity,
    ValidationStatus,
)

# ── shared test data ──────────────────────────────────────────────────────────

DATASET_ID = "dset-test00000000000000000000000000"
RUN_ID = "run-test000000000000000000000000000"


def _prov() -> Provenance:
    return Provenance(
        producer="test.producer",
        version="1.0.0",
        params={},
        input_digest="a" * 64,
        duration_ms=1,
        seed=None,
    )


def _make_finding(col: str = "col_a", rate: float = 0.10) -> Finding:
    msr = Measurement.create(
        dataset_id=DATASET_ID,
        type="core.quality.missing",
        scope=Scope(kind=ScopeKind.COLUMN, refs=(col,)),
        payload={
            "total_count": 100,
            "missing_count": int(rate * 100),
            "missing_proportion": rate,
        },
        provenance=_prov(),
    )
    return Finding.create(
        dataset_id=DATASET_ID,
        type="core.finding.missing_rate",
        scope=Scope(kind=ScopeKind.COLUMN, refs=(col,)),
        statement=(
            f"Taxa de ausência elevada ({rate:.1%}, "
            f"{int(rate * 100)}/100, limiar=5%)."
        ),
        severity=Severity.FAIL,
        derived_from=(msr.id,),
        rule="core.finding.missing_rate",
        rule_version="1.0.0",
        params={
            "missing_proportion": rate,
            "total_count": 100,
            "missing_count": int(rate * 100),
            "warn_threshold": 0.05,
            "null_sentinels_applied": [],
        },
    )


def _make_assessment(fnd: Finding) -> Assessment:
    return Assessment.create(
        dataset_id=DATASET_ID,
        type="core.assessment.data_quality",
        scope=Scope(kind=ScopeKind.DATASET, refs=(DATASET_ID,)),
        goal="data_quality",
        verdict="unacceptable",
        severity=Severity.FAIL,
        derived_from=(fnd.id,),
        rule="core.assessment.data_quality",
        rule_version="1.0.0",
        policy={"fail_threshold": 0.0},
    )


def _run_report(
    findings: list[Finding],
    assessments: list[Assessment],
    composer_responses: list[str],
    judge_responses: list[str] | None = None,
) -> ReportResult:
    return generate_report(
        findings=findings,
        assessments=assessments,
        composer_model=StubLanguageModel(composer_responses),
        judge_model=StubLanguageModel(
            judge_responses if judge_responses is not None else ["entailed"] * 50
        ),
        run_id=RUN_ID,
        dataset_id=DATASET_ID,
    )


# ── isolation test ────────────────────────────────────────────────────────────


class TestComposerIsolation:
    def test_generate_report_signature_excludes_raw_data(self) -> None:
        """generate_report must not accept Dataset, Measurement, or Artifact.

        This is a structural enforcement test: adding any of these parameters
        to the function causes this test to fail at import time.
        """
        sig = inspect.signature(generate_report)
        param_names = set(sig.parameters)
        forbidden = {
            "dataset", "measurement", "measurements",
            "artifact", "artifacts", "table", "rows",
            "dataframe", "raw_data",
        }
        violations = forbidden & param_names
        assert not violations, (
            f"generate_report must not accept raw-data parameters: {violations}"
        )

    def test_serialize_sources_contains_finding_id_and_statement(self) -> None:
        fnd = _make_finding()
        ast = _make_assessment(fnd)
        result = _serialize_sources([fnd], [ast])
        assert fnd.id in result
        assert fnd.statement in result

    def test_serialize_sources_contains_assessment_id_and_goal(self) -> None:
        fnd = _make_finding()
        ast = _make_assessment(fnd)
        result = _serialize_sources([fnd], [ast])
        assert ast.id in result
        assert ast.goal in result

    def test_serialize_sources_never_contains_msr_prefix(self) -> None:
        """Serialized sources must not contain Measurement IDs."""
        fnd = _make_finding()
        ast = _make_assessment(fnd)
        result = _serialize_sources([fnd], [ast])
        assert "msr-" not in result

    def test_claim_supports_rejects_artifact_id(self) -> None:
        """Claim model enforces that supports can only be fnd-/ast-."""
        fake_art = "art-" + "a" * 32
        with pytest.raises(ValueError, match=r"fnd-.*ast-|ast-.*fnd-"):
            Claim.create(
                dataset_id=DATASET_ID,
                run_id=RUN_ID,
                text="Some text.",
                supports=(fake_art,),
                validation=None,  # type: ignore[arg-type]
            )


# ── generation and claim creation ─────────────────────────────────────────────


class TestReportGeneration:
    def test_correct_sentence_becomes_claim(self) -> None:
        fnd = _make_finding("renda", 0.076)
        text = f"A coluna renda tem taxa de ausência de 7,6% [{fnd.id}]."
        result = _run_report([fnd], [], [text])
        assert len(result.claims) == 1
        assert result.claims[0].text == text

    def test_claim_has_correct_supports(self) -> None:
        fnd = _make_finding("renda", 0.076)
        text = f"Taxa elevada [{fnd.id}]."
        result = _run_report([fnd], [], [text])
        assert fnd.id in result.claims[0].supports

    def test_claim_validation_status_is_passed(self) -> None:
        fnd = _make_finding("renda", 0.076)
        text = f"Taxa elevada [{fnd.id}]."
        result = _run_report([fnd], [], [text])
        assert result.claims[0].validation.status == ValidationStatus.PASSED

    def test_multiple_sentences_each_become_claim(self) -> None:
        fnd1 = _make_finding("col_a", 0.10)
        fnd2 = _make_finding("col_b", 0.20)
        s1 = f"Coluna col_a tem 10,0% ausência [{fnd1.id}]."
        s2 = f"Coluna col_b tem 20,0% ausência [{fnd2.id}]."
        result = _run_report([fnd1, fnd2], [], [f"{s1} {s2}"])
        assert len(result.claims) == 2

    def test_claim_id_is_deterministic(self) -> None:
        fnd = _make_finding("renda", 0.076)
        text = f"Taxa elevada [{fnd.id}]."
        r1 = _run_report([fnd], [], [text])
        r2 = _run_report([fnd], [], [text])
        assert r1.claims[0].id == r2.claims[0].id

    def test_assessment_citation_creates_valid_claim(self) -> None:
        fnd = _make_finding()
        ast = _make_assessment(fnd)
        text = f"Qualidade inaceitável [{ast.id}]."
        result = _run_report([fnd], [ast], [text])
        assert len(result.claims) == 1
        assert ast.id in result.claims[0].supports


# ── rejection flow ────────────────────────────────────────────────────────────


class TestRejectionFlow:
    def test_sentence_without_citation_rejected_then_rewrite_passes(self) -> None:
        fnd = _make_finding()
        result = _run_report(
            [fnd], [],
            [
                "Sem citação alguma.",       # attempt 1 — no citation
                f"Com citação [{fnd.id}].",  # rewrite — passes
            ],
        )
        assert len(result.claims) == 1
        assert len(result.rejected) == 1
        assert result.rejected[0].reason_code == "no_citation"
        assert result.rejected[0].attempt == 1

    def test_sentence_with_unknown_id_is_rejected(self) -> None:
        fnd = _make_finding()
        bad_id = "fnd-" + "0" * 32
        result = _run_report(
            [fnd], [],
            [
                f"Cita ID inexistente [{bad_id}].",
                f"Cita ID válido [{fnd.id}].",
            ],
        )
        assert result.rejected[0].reason_code == "unknown_citation"

    def test_two_failures_discard_sentence(self) -> None:
        fnd = _make_finding()
        result = _run_report(
            [fnd], [],
            ["Sem citação.", "Sem citação."],
        )
        assert result.metrics.discarded == 1
        assert result.claims == []

    def test_rejection_records_capture_layer_and_attempt(self) -> None:
        fnd = _make_finding()
        result = _run_report(
            [fnd], [],
            ["Sem citação.", "Sem citação."],
        )
        assert len(result.rejected) == 2
        assert result.rejected[0].attempt == 1
        assert result.rejected[1].attempt == 2

    def test_pass_on_second_attempt_records_attempt_count(self) -> None:
        fnd = _make_finding("renda", 0.076)
        good = f"Taxa de 7,6% [{fnd.id}]."
        result = _run_report(
            [fnd], [],
            ["Sem citação.", good],
        )
        assert len(result.claims) == 1
        assert result.claims[0].validation.attempts == 2

    def test_discarded_sentence_not_in_claims(self) -> None:
        fnd = _make_finding()
        result = _run_report([fnd], [], ["Sem citação.", "Sem citação."])
        claim_texts = [c.text for c in result.claims]
        assert all("Sem citação" not in t for t in claim_texts)


# ── metrics ───────────────────────────────────────────────────────────────────


class TestMetrics:
    def test_total_sentences_counts_each_sentence_once(self) -> None:
        fnd = _make_finding()
        s1 = f"Ok [{fnd.id}]."
        s2 = f"Ok também [{fnd.id}]."
        result = _run_report([fnd], [], [f"{s1} {s2}"])
        assert result.metrics.total_sentences == 2

    def test_rejected_layer1_counts_correctly(self) -> None:
        fnd = _make_finding()
        result = _run_report(
            [fnd], [],
            ["Sem citação.", f"Com citação [{fnd.id}]."],
        )
        assert result.metrics.rejected_layer1 == 1

    def test_discarded_counted_separately_from_rejected(self) -> None:
        fnd = _make_finding()
        result = _run_report([fnd], [], ["Sem citação.", "Sem citação."])
        assert result.metrics.discarded == 1
        assert result.metrics.rejected_layer1 == 2  # both attempts rejected L1

    def test_discard_rate_on_all_discarded(self) -> None:
        fnd = _make_finding()
        result = _run_report([fnd], [], ["Sem citação.", "Sem citação."])
        assert result.metrics.discard_rate == 1.0

    def test_rejection_rate_by_layer_keys(self) -> None:
        fnd = _make_finding()
        result = _run_report([fnd], [], [f"Ok [{fnd.id}]."])
        rates = result.metrics.rejection_rate_by_layer
        assert set(rates) == {"syntactic", "numeric", "semantic"}

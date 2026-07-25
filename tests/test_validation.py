"""Tests for core.validation — three layers tested independently.

Layer 1 (syntactic): citation presence and ID validity.
Layer 2 (numeric):   number extraction and source matching.
Layer 3 (semantic):  entailment via stub judge.
Validator:           orchestration and stop-at-first-failure.
"""

from __future__ import annotations

from typing import cast

from core.llm import StubLanguageModel
from core.model import (
    Assessment,
    Finding,
    Measurement,
    Provenance,
    Scope,
    ScopeKind,
    Severity,
    ValidationLayer,
    ValidationVerdict,
)
from core.validation._layer1 import check_syntactic
from core.validation._layer2 import check_numeric, extract_br_numbers
from core.validation._layer3 import check_semantic
from core.validation._validator import Validator

# ── shared fixtures ───────────────────────────────────────────────────────────

DATASET_ID = "dset-test00000000000000000000000000"


def _prov() -> Provenance:
    return Provenance(
        producer="test.producer",
        version="1.0.0",
        params={},
        input_digest="a" * 64,
        duration_ms=1,
        seed=None,
    )


def _make_finding(
    *,
    missing_proportion: float = 0.076,
    total: int = 912,
    missing: int = 69,
    col: str = "renda_mensal",
) -> Finding:
    msr = Measurement.create(
        dataset_id=DATASET_ID,
        type="core.quality.missing",
        scope=Scope(kind=ScopeKind.COLUMN, refs=(col,)),
        payload={
            "total_count": total,
            "missing_count": missing,
            "missing_proportion": missing_proportion,
        },
        provenance=_prov(),
    )
    return Finding.create(
        dataset_id=DATASET_ID,
        type="core.finding.missing_rate",
        scope=Scope(kind=ScopeKind.COLUMN, refs=(col,)),
        statement=(
            f"Taxa de ausência elevada ({missing_proportion:.1%},"
            f" {missing}/{total}, limiar=5%)."
        ),
        severity=Severity.FAIL,
        derived_from=(msr.id,),
        rule="core.finding.missing_rate",
        rule_version="1.0.0",
        params={
            "missing_proportion": missing_proportion,
            "total_count": total,
            "missing_count": missing,
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


# ── Layer 1 — syntactic ───────────────────────────────────────────────────────


class TestLayer1Syntactic:
    def setup_method(self) -> None:
        self.fnd = _make_finding()
        self.ast = _make_assessment(self.fnd)
        self.valid_ids = frozenset([self.fnd.id, self.ast.id])

    def test_sentence_without_citation_fails(self) -> None:
        c = check_syntactic("Nenhuma citação aqui.", self.valid_ids)
        assert c.verdict == ValidationVerdict.FAIL
        assert c.reason_code == "no_citation"

    def test_sentence_with_valid_fnd_citation_passes(self) -> None:
        c = check_syntactic(f"Texto [{self.fnd.id}].", self.valid_ids)
        assert c.verdict == ValidationVerdict.PASS
        assert c.reason_code == "ok"

    def test_sentence_with_valid_ast_citation_passes(self) -> None:
        c = check_syntactic(f"Texto [{self.ast.id}].", self.valid_ids)
        assert c.verdict == ValidationVerdict.PASS

    def test_unknown_fnd_id_fails(self) -> None:
        bad = "fnd-" + "9" * 32
        c = check_syntactic(f"Cita ID inexistente [{bad}].", self.valid_ids)
        assert c.verdict == ValidationVerdict.FAIL
        assert c.reason_code == "unknown_citation"
        assert bad in cast("list[str]", c.detail["unknown_ids"])

    def test_msr_prefix_is_not_valid_citation(self) -> None:
        msr_id = "msr-" + "a" * 32
        c = check_syntactic(f"Cita msr [{msr_id}].", self.valid_ids)
        assert c.verdict == ValidationVerdict.FAIL
        assert c.reason_code == "no_citation"

    def test_art_prefix_is_not_valid_citation(self) -> None:
        art_id = "art-" + "a" * 32
        c = check_syntactic(f"Veja o gráfico [{art_id}].", self.valid_ids)
        assert c.verdict == ValidationVerdict.FAIL
        assert c.reason_code == "no_citation"

    def test_multiple_valid_citations_pass(self) -> None:
        sentence = f"A e B [{self.fnd.id}] [{self.ast.id}]."
        c = check_syntactic(sentence, self.valid_ids)
        assert c.verdict == ValidationVerdict.PASS

    def test_mix_valid_and_invalid_citations_fails(self) -> None:
        bad = "fnd-" + "0" * 32
        sentence = f"Texto [{self.fnd.id}] [{bad}]."
        c = check_syntactic(sentence, self.valid_ids)
        assert c.verdict == ValidationVerdict.FAIL
        assert c.reason_code == "unknown_citation"

    def test_empty_valid_ids_fails(self) -> None:
        any_id = "fnd-" + "a" * 32
        c = check_syntactic(f"[{any_id}].", frozenset())
        assert c.verdict == ValidationVerdict.FAIL

    def test_duration_ms_is_non_negative(self) -> None:
        c = check_syntactic("Sem citação.", self.valid_ids)
        assert c.duration_ms >= 0


# ── Layer 2 — numeric extraction ─────────────────────────────────────────────


class TestBrNumberExtraction:
    """Unit tests for the Brazilian number extractor used by Layer 2."""

    def test_plain_integer(self) -> None:
        assert extract_br_numbers("69 linhas") == [(69.0, False)]

    def test_decimal_comma(self) -> None:
        result = extract_br_numbers("7,6%")
        assert len(result) == 1
        assert abs(result[0][0] - 7.6) < 0.001
        assert result[0][1] is True

    def test_thousands_separator_period(self) -> None:
        result = extract_br_numbers("1.234 registros")
        assert len(result) == 1
        assert abs(result[0][0] - 1234.0) < 0.001

    def test_thousands_plus_decimal(self) -> None:
        result = extract_br_numbers("1.234,56")
        assert len(result) == 1
        assert abs(result[0][0] - 1234.56) < 0.001

    def test_percentage_flag(self) -> None:
        result = extract_br_numbers("1,32%")
        assert result[0][1] is True

    def test_no_percentage_flag(self) -> None:
        result = extract_br_numbers("69 linhas")
        assert result[0][1] is False

    def test_multiple_numbers(self) -> None:
        result = extract_br_numbers("69/912 e 7,6%")
        values = [v for v, _ in result]
        assert 69.0 in values
        assert 912.0 in values

    def test_zero(self) -> None:
        result = extract_br_numbers("0 ausências")
        assert result[0][0] == 0.0

    def test_no_numbers_returns_empty(self) -> None:
        assert extract_br_numbers("sem números aqui") == []


# ── Layer 2 — numeric validation ─────────────────────────────────────────────


class TestLayer2Numeric:
    def setup_method(self) -> None:
        self.fnd = _make_finding(
            missing_proportion=0.076, total=912, missing=69
        )
        self.ast = _make_assessment(self.fnd)

    def test_sentence_with_correct_proportion_passes(self) -> None:
        sentence = f"Taxa de 7,6% [{self.fnd.id}]."
        c = check_numeric(sentence, [self.fnd], [], tolerance=0.005)
        assert c.verdict == ValidationVerdict.PASS

    def test_sentence_with_correct_count_passes(self) -> None:
        sentence = f"Há 69 valores ausentes [{self.fnd.id}]."
        c = check_numeric(sentence, [self.fnd], [], tolerance=0.005)
        assert c.verdict == ValidationVerdict.PASS

    def test_sentence_with_wrong_number_fails(self) -> None:
        sentence = f"Taxa de 99,9% [{self.fnd.id}]."
        c = check_numeric(sentence, [self.fnd], [], tolerance=0.005)
        assert c.verdict == ValidationVerdict.FAIL
        assert c.reason_code == "unsupported_number"
        assert "99.9%" in cast("list[str]", c.detail["unsupported"])

    def test_adultered_count_fails(self) -> None:
        sentence = f"Há 100 valores ausentes [{self.fnd.id}]."
        # 100 is not in params (total=912, missing=69, proportion=0.076, threshold=0.05)
        c = check_numeric(sentence, [self.fnd], [], tolerance=0.005)
        assert c.verdict == ValidationVerdict.FAIL

    def test_sentence_without_numbers_passes(self) -> None:
        sentence = f"A qualidade está comprometida [{self.fnd.id}]."
        c = check_numeric(sentence, [self.fnd], [], tolerance=0.005)
        assert c.verdict == ValidationVerdict.PASS
        assert c.reason_code == "no_numbers"

    def test_boundary_within_tolerance_passes(self) -> None:
        # proportion=0.076; 7,6% → 7.6/100 = 0.076. Test at boundary.
        sentence = f"Taxa de 7,6% [{self.fnd.id}]."
        c = check_numeric(sentence, [self.fnd], [], tolerance=0.005)
        assert c.verdict == ValidationVerdict.PASS

    def test_boundary_slightly_outside_tolerance_fails(self) -> None:
        # 8,2% → 0.082 — not in params (closest is 0.076, diff=0.006 > 0.005)
        sentence = f"Taxa de 8,2% [{self.fnd.id}]."
        c = check_numeric(sentence, [self.fnd], [], tolerance=0.005)
        assert c.verdict == ValidationVerdict.FAIL

    def test_percentage_proportion_both_accepted(self) -> None:
        # 7,6% → candidates [7.6, 0.076]; params has 0.076 → pass
        sentence = f"Ausência de 7,6% [{self.fnd.id}]."
        c = check_numeric(sentence, [self.fnd], [], tolerance=0.005)
        assert c.verdict == ValidationVerdict.PASS

    def test_threshold_in_params_passes(self) -> None:
        # warn_threshold=0.05 → 5,0% in sentence
        sentence = f"Limiar de 5,0% [{self.fnd.id}]."
        c = check_numeric(sentence, [self.fnd], [], tolerance=0.005)
        assert c.verdict == ValidationVerdict.PASS

    def test_configurable_tolerance(self) -> None:
        # 8,0% → 0.08; closest is 0.076 (diff=0.004).
        # Fails at tol=0.003, passes at 0.005.
        sentence = f"Taxa de 8,0% [{self.fnd.id}]."
        assert (
            check_numeric(sentence, [self.fnd], [], tolerance=0.003).verdict
            == ValidationVerdict.FAIL
        )
        assert (
            check_numeric(sentence, [self.fnd], [], tolerance=0.005).verdict
            == ValidationVerdict.PASS
        )

    def test_assessment_policy_values_used_as_source(self) -> None:
        # policy has fail_threshold=0.0; sentence cites ast
        sentence = f"Limiar de falha em 0 [{self.ast.id}]."
        c = check_numeric(sentence, [], [self.ast], tolerance=0.005)
        assert c.verdict == ValidationVerdict.PASS

    def test_wrong_number_with_multiple_sources_still_fails(self) -> None:
        sentence = f"Número falso de 42,0% [{self.fnd.id}]."
        c = check_numeric(sentence, [self.fnd], [], tolerance=0.005)
        assert c.verdict == ValidationVerdict.FAIL

    def test_duplicate_rate_numbers(self) -> None:
        """Real scenario: 12 duplicate rows, 1,32%, 912 total."""
        msr = Measurement.create(
            dataset_id=DATASET_ID,
            type="core.quality.row_dedup",
            scope=Scope(kind=ScopeKind.DATASET, refs=(DATASET_ID,)),
            payload={
                "total_rows": 912,
                "unique_rows": 900,
                "duplicate_rows": 12,
                "duplicate_proportion": 12 / 912,
            },
            provenance=_prov(),
        )
        fnd = Finding.create(
            dataset_id=DATASET_ID,
            type="core.finding.duplicate_rate",
            scope=Scope(kind=ScopeKind.DATASET, refs=(DATASET_ID,)),
            statement="Taxa de duplicação elevada (1,32%, 12/912 linhas, limiar=1%).",
            severity=Severity.FAIL,
            derived_from=(msr.id,),
            rule="core.finding.duplicate_rate",
            rule_version="1.0.0",
            params={
                "duplicate_rows": 12,
                "total_rows": 912,
                "duplicate_rate": 12 / 912,
                "warn_threshold": 0.01,
            },
        )
        sentence = f"O dataset tem 12 linhas duplicadas (1,32%) [{fnd.id}]."
        c = check_numeric(sentence, [fnd], [], tolerance=0.005)
        assert c.verdict == ValidationVerdict.PASS


# ── Layer 3 — semantic ────────────────────────────────────────────────────────


class TestLayer3Semantic:
    def setup_method(self) -> None:
        self.fnd = _make_finding()

    def _check(self, judge_response: str) -> bool:
        sentence = f"Texto qualquer [{self.fnd.id}]."
        judge = StubLanguageModel([judge_response])
        c = check_semantic(sentence, [self.fnd], [], judge)
        return c.verdict == ValidationVerdict.PASS

    def test_entailed_passes(self) -> None:
        assert self._check("entailed") is True

    def test_unsupported_fails(self) -> None:
        assert self._check("unsupported") is False

    def test_contradicted_fails(self) -> None:
        assert self._check("contradicted") is False

    def test_unparseable_response_treated_as_unsupported(self) -> None:
        assert self._check("maybe") is False

    def test_case_insensitive_response(self) -> None:
        assert self._check("ENTAILED") is True

    def test_reason_code_matches_verdict(self) -> None:
        sentence = f"Texto [{self.fnd.id}]."
        judge = StubLanguageModel(["contradicted"])
        c = check_semantic(sentence, [self.fnd], [], judge)
        assert c.reason_code == "contradicted"

    def test_isolation_judge_receives_only_cited_sources(self) -> None:
        """The judge prompt must not contain content from uncited findings."""
        fnd_cited = _make_finding(col="renda")
        fnd_other = _make_finding(col="satisfacao")
        sentence = f"Texto [{fnd_cited.id}]."

        captured_prompts: list[str] = []

        class CapturingStub:
            def complete(self, prompt: str) -> str:
                captured_prompts.append(prompt)
                return "entailed"

        check_semantic(sentence, [fnd_cited], [], CapturingStub())
        assert len(captured_prompts) == 1
        # cited finding appears in prompt
        assert fnd_cited.id in captured_prompts[0]
        # uncited finding does NOT appear
        assert fnd_other.id not in captured_prompts[0]

    def test_duration_ms_non_negative(self) -> None:
        sentence = f"Texto [{self.fnd.id}]."
        judge = StubLanguageModel(["entailed"])
        c = check_semantic(sentence, [self.fnd], [], judge)
        assert c.duration_ms >= 0


# ── Validator orchestration ───────────────────────────────────────────────────


class TestValidator:
    def setup_method(self) -> None:
        self.fnd = _make_finding()
        self.ast = _make_assessment(self.fnd)

    def _v(self, judge_response: str = "entailed") -> Validator:
        return Validator(judge=StubLanguageModel([judge_response] * 20))

    def test_valid_sentence_passes_all_layers(self) -> None:
        sentence = f"Taxa de 7,6% [{self.fnd.id}]."
        passed, checks = self._v().validate(sentence, [self.fnd], [])
        assert passed is True
        assert len(checks) == 3

    def test_no_citation_stops_at_layer1(self) -> None:
        passed, checks = self._v().validate("Sem citação.", [self.fnd], [])
        assert passed is False
        assert len(checks) == 1
        assert checks[0].layer == ValidationLayer.SYNTACTIC

    def test_wrong_number_stops_at_layer2(self) -> None:
        sentence = f"Taxa de 99,9% [{self.fnd.id}]."
        passed, checks = self._v().validate(sentence, [self.fnd], [])
        assert passed is False
        assert len(checks) == 2
        assert checks[-1].layer == ValidationLayer.NUMERIC

    def test_semantic_fail_stops_at_layer3(self) -> None:
        sentence = f"Taxa de 7,6% [{self.fnd.id}]."
        passed, checks = Validator(
            judge=StubLanguageModel(["contradicted"])
        ).validate(sentence, [self.fnd], [])
        assert passed is False
        assert len(checks) == 3
        assert checks[-1].layer == ValidationLayer.SEMANTIC

    def test_sentence_with_no_numbers_skips_numeric_to_semantic(self) -> None:
        sentence = f"Qualidade comprometida [{self.fnd.id}]."
        passed, checks = self._v("entailed").validate(
            sentence, [self.fnd], []
        )
        assert passed is True
        layers = [c.layer for c in checks]
        assert ValidationLayer.NUMERIC in layers
        assert ValidationLayer.SEMANTIC in layers

    def test_unknown_id_fails_layer1_not_layer2(self) -> None:
        bad_id = "fnd-" + "f" * 32
        sentence = f"Texto [{bad_id}]."
        passed, checks = self._v().validate(sentence, [self.fnd], [])
        assert passed is False
        assert checks[0].layer == ValidationLayer.SYNTACTIC
        assert checks[0].reason_code == "unknown_citation"

    def test_assessment_cited_correctly(self) -> None:
        sentence = f"Qualidade inaceitável [{self.ast.id}]."
        passed, _ = self._v().validate(sentence, [self.fnd], [self.ast])
        assert passed is True

    def test_configurable_tolerance_propagated(self) -> None:
        sentence = f"Taxa de 8,0% [{self.fnd.id}]."
        # diff=0.004; tight tolerance=0.003 → fail, loose=0.005 → pass
        tight = Validator(
            judge=StubLanguageModel(["entailed"]), tolerance=0.003
        )
        loose = Validator(
            judge=StubLanguageModel(["entailed"]), tolerance=0.005
        )
        passed_tight, _ = tight.validate(sentence, [self.fnd], [])
        passed_loose, _ = loose.validate(sentence, [self.fnd], [])
        assert passed_tight is False
        assert passed_loose is True

"""Generate Claims with controlled, genuine rejections for the validation panel.

Strategy (no fake data — every rejection comes from the real validator):

  SYNTACTIC rejection: sentence with no citation bracket. Both retry attempts
    also lack citations, so the sentence is discarded after 2 rejections.

  NUMERIC rejection: sentence citing fnd_renda (renda_mensal missing_rate) with
    an adultered value of 45,3% instead of the real 7,6% stored in Finding.params.
    Layer 2 rejects because 45.3 does not appear in any reachable numeric value
    within tolerance. The retry rewrites to a citation-only sentence (no numbers),
    which passes all layers and becomes a Claim.

  SEMANTIC rejection: sentence that cites ast_quality (verdict=unacceptable) but
    claims the dataset is in "excelente condição" — a genuine contradiction. The
    judge stub returns "contradicted" whenever the prompt contains "excelente
    condição"; the retry uses an accurate sentence and passes all layers.

The _split_sentences regex splits on [.!?]+whitespace+[A-Z...], so all four
sentences must start with a capital letter. No underscore-prefixed sentinels.

Rejected sentences are persisted to claim_rejections via rejection_repo.
Sentences that pass (including on retry) are persisted to claims.
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from dotenv import load_dotenv

load_dotenv()

from core.composer import generate_report
from core.llm import LanguageModel, StubLanguageModel
from db.connection import get_connection
from db.repos import assessments as assessment_repo
from db.repos import claims as claim_repo
from db.repos import findings as finding_repo
from db.repos import rejections as rejection_repo

RUN_ID = "run-c10935da11af973f5d4a7d7689d63a1f"
DATASET_ID = "dset-d51f7a6bd037b3c3414849ce5400c6a6"

# Real IDs from the database
fnd_renda = (
    "fnd-3f30434a7da1794ae0c594f84499a9d7"  # missing_rate renda_mensal (real: 7,6%)
)
ast_quality = "ast-ac190783bf60aa73d97a0cdd363cc311"  # verdict=unacceptable
ast_model = "ast-d155825d6e411e4adc03a5027ea2bc19"

# ── sentence design ───────────────────────────────────────────────────────────

# Sentence 1: SYNTACTIC — no citation at all. Layer 1 rejects both attempts.
_SYN_BAD = "Problemas de qualidade foram identificados e requerem tratamento imediato."
_SYN_BAD2 = (
    "Associações relevantes também foram observadas entre as variáveis numéricas."
)

# Sentence 2: NUMERIC — adultered value 45,3% vs real 7,6% in Finding.params.
# Layer 2 rejects attempt 1. Retry writes a number-free sentence that passes.
_NUM_BAD = f"A coluna 'renda_mensal' apresenta 45,3% de valores ausentes [{fnd_renda}]."
_NUM_GOOD = (
    f"A coluna 'renda_mensal' registra taxa de ausência acima do limiar"
    f" configurado [{fnd_renda}]."
)

# Sentence 3: SEMANTIC — cites ast_quality (verdict=unacceptable) but claims
# "excelente condição". The judge stub recognises this contradiction and returns
# "contradicted". Retry uses an accurate sentence.
_SEM_BAD = (
    f"O dataset se encontra em excelente condição para uso direto [{ast_quality}]."
)
_SEM_GOOD = (
    f"O dataset foi classificado como inaceitável para uso direto"
    f" sem tratamento prévio [{ast_quality}]."
)

# Sentence 4: passes all layers on first try — good baseline.
_OK = (
    f"A avaliação de modelagem indica que o dataset não satisfaz os requisitos"
    f" de elegibilidade [{ast_model}]."
)

# Composer stub:
#   Call 0: initial report (all 4 sentences as a single text)
#   Call 1: rewrite of SYN_BAD → SYN_BAD2 (still no citation, discarded)
#   Call 2: rewrite of NUM_BAD → NUM_GOOD (passes, becomes Claim)
#   Call 3: rewrite of SEM_BAD → SEM_GOOD (passes, becomes Claim)
_COMPOSER_REPORT = f"{_SYN_BAD} {_NUM_BAD} {_SEM_BAD} {_OK}"
composer_stub = StubLanguageModel([_COMPOSER_REPORT, _SYN_BAD2, _NUM_GOOD, _SEM_GOOD])


# ── semantic judge stub ───────────────────────────────────────────────────────


class SemanticKeywordJudge:
    """Returns 'contradicted' when the prompt contains the contradiction phrase.

    The phrase 'excelente condição' genuinely contradicts ast_quality whose
    verdict is 'unacceptable'. A real LLM would return 'contradicted' for the
    same reason. This stub simulates that response deterministically.
    """

    def complete(self, prompt: str) -> str:
        if "excelente condição" in prompt:
            return "contradicted"
        return "entailed"


judge_stub: LanguageModel = SemanticKeywordJudge()

# ── run ───────────────────────────────────────────────────────────────────────

conn = get_connection()
findings = finding_repo.list_by_run(conn, RUN_ID)
assessments = assessment_repo.list_by_run(conn, RUN_ID)

result = generate_report(
    findings=findings,
    assessments=assessments,
    composer_model=composer_stub,
    judge_model=judge_stub,
    run_id=RUN_ID,
    dataset_id=DATASET_ID,
)

print(f"Sentenças geradas:  {result.metrics.total_sentences}")
print(f"Claims aprovados:   {len(result.claims)}")
print(f"Rejeições totais:   {len(result.rejected)}")
print(f"Descartados:        {result.metrics.discarded}")
print()

for r in result.rejected:
    print(
        f"  [REJEITADO] camada={r.layer.value}"
        f" motivo={r.reason_code} tentativa={r.attempt}"
    )
    print(f"             texto: {r.text[:80]!r}")
    rejection_repo.upsert(conn, RUN_ID, r)

for c in result.claims:
    claim_repo.upsert(conn, c)
    print(f"  [CLAIM OK] {c.id}")
    print(f"             {c.text[:80]}...")

conn.commit()
conn.close()
print(
    f"\nGravado: {len(result.rejected)} rejeição(ões) em claim_rejections,"
    f" {len(result.claims)} claim(s) em claims."
)

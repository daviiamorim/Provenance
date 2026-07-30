"""Generate and persist Claims for the colaboradores.csv run using stubs.

Composer stub: returns 5 hand-crafted sentences that cite real finding/assessment
IDs from the database, no numbers (layer 2 passes trivially).
Judge stub: always returns 'entailed' (layer 3 passes).

This is the correct approach for a dev environment without an LLM API key.
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from dotenv import load_dotenv

load_dotenv()

from core.composer import generate_report
from core.llm import StubLanguageModel
from db.connection import get_connection
from db.repos import assessments as assessment_repo
from db.repos import claims as claim_repo
from db.repos import findings as finding_repo

RUN_ID = "run-c10935da11af973f5d4a7d7689d63a1f"
DATASET_ID = "dset-d51f7a6bd037b3c3414849ce5400c6a6"

conn = get_connection()
findings = finding_repo.list_by_run(conn, RUN_ID)
assessments = assessment_repo.list_by_run(conn, RUN_ID)

# Build the IDs index for reference
fnd_by_type: dict[str, str] = {}
for f in findings:
    fnd_by_type[f"{f.type}:{','.join(f.scope.refs)}"] = f.id

# Hand-crafted report text using the actual IDs from this run.
# No numbers in sentences → layer 2 validation passes trivially.
# All IDs are real → layer 1 validation passes.
fnd_renda = "fnd-3f30434a7da1794ae0c594f84499a9d7"
fnd_satisf = "fnd-b8d99d19e7b5e42f4c09f3c929f733d3"
fnd_dupl = "fnd-2eaa1ad84e91ccd12fcc27dc392c4175"
fnd_assoc = "fnd-8046d98deb3c844d9b069570a9679257"
fnd_horas = "fnd-101438112e782a1eb2a4c85e7f7ba8bd"
ast_quality = "ast-ac190783bf60aa73d97a0cdd363cc311"
ast_model = "ast-d155825d6e411e4adc03a5027ea2bc19"

REPORT_TEXT = (
    f"O dataset de colaboradores apresenta ausência expressiva de valores nas colunas"
    f" 'renda_mensal' e 'satisfacao', conforme registrado em"
    f" [{fnd_renda}] e [{fnd_satisf}]. "
    f"Foram identificados registros duplicados em proporção acima do limiar configurado"
    f" [{fnd_dupl}]. "
    f"A coluna 'horas_mes' exibe taxa de ausência baixa, mas não nula [{fnd_horas}]. "
    f"Existe associação moderada e positiva entre as variáveis 'horas_mes' e"
    f" 'produtividade' [{fnd_assoc}]. "
    f"A avaliação de qualidade concluiu que o dataset está em condição inaceitável"
    f" para uso direto, exigindo tratamento dos valores ausentes antes de qualquer"
    f" análise [{ast_quality}]. "
    f"O dataset não satisfaz os requisitos de elegibilidade para modelagem preditiva"
    f" sem pré-processamento dos problemas identificados [{ast_model}]."
)

composer_stub = StubLanguageModel([REPORT_TEXT])
judge_stub = StubLanguageModel(["entailed"])

result = generate_report(
    findings=findings,
    assessments=assessments,
    composer_model=composer_stub,
    judge_model=judge_stub,
    run_id=RUN_ID,
    dataset_id=DATASET_ID,
)

print(f"Sentenças geradas: {result.metrics.total_sentences}")
print(f"Claims aprovados:  {len(result.claims)}")
print(f"Rejeitados:        {len(result.rejected)}")
print(f"Descartados:       {result.metrics.discarded}")
print()

for c in result.claims:
    claim_repo.upsert(conn, c)
    print(f"  Salvo: {c.id}")
    print(f"         {c.text[:80]}...")

conn.commit()
conn.close()
print("\nClaims gravados no banco.")

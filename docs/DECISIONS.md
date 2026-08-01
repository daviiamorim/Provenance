# Decisões de arquitetura e dependências

## 2026-07-24 — hypothesis fixado em <6.112

A partir de hypothesis 6.112, o pacote inclui `_native.cp313-win_amd64.pyd`, uma extensão Rust compilada sem assinatura Authenticode. A política WDAC ativa nesta máquina (ID `{0283ac0f-fff1-49ae-ada1-8a933130cad6}`) bloqueia o carregamento de qualquer binário não assinado no nível do kernel, antes de o Python conseguir importar o módulo. O resultado é `ImportError` na coleta dos testes — a suíte inteira falha sem rodar nenhum caso.

Hypothesis 6.111.x é Python puro (zero extensões binárias) e comportamentalmente idêntico para os testes deste projeto. O pin `hypothesis>=6.0,<6.112` está em `pyproject.toml`.

**Para desbloquear versões mais novas:** resolver a política WDAC antes de remover o pin. Não remova sem isso — os testes voltam a falhar na coleta.

---

## 2026-07-24 — Etapa 3: regras de Finding e Assessment

### Princípio: p-valor não é critério de severidade

p-valores são rejeitados como critério de severidade nas regras de Finding. O problema é inflação por tamanho amostral: com n suficientemente grande, qualquer desvio trivial da hipótese nula produz p < 0,05, mesmo que o efeito seja irrelevante na prática. Para n = 5 000, um Shapiro-Wilk pode rejeitar a normalidade com p = 0,0001 mesmo quando W = 0,97 (distribuição essencialmente normal).

As regras usam estatísticas de tamanho de efeito:
- **Shapiro-Wilk**: critério é W (0 a 1), não p.
- **D'Agostino-Pearson**: critério é assimetria e curtose do Measurement descritivo, não K².
- **Correlação**: critério é |r| (coeficiente), não p.

O campo `p_value` existe nos Measurements e é armazenado como evidência bruta, mas as regras de Finding não o leem.

---

### Limiares das regras de Finding

Todos os limiares são armazenados em `Finding.params` para que o auditor saiba contra qual régua a coluna foi julgada.

#### `core.finding.distribution_shape`

| Parâmetro | Valor | Origem |
|---|---|---|
| `threshold_ok` (SW) | 0,95 | Convenção prática amplamente usada em guias de estatística aplicada. Sem derivação teórica. **Ajustável.** |
| `threshold_warn` (SW) | 0,90 | Idem. |
| `skewness_threshold_ok` | 0,50 | Bulmer (1979) "Principles of Statistics": \|skew\| < 0,5 = "razoavelmente simétrico". Heurística citável. |
| `skewness_threshold_warn` | 1,00 | Bulmer (1979): 0,5–1,0 = "assimetria moderada"; ≥ 1,0 = "altamente assimétrico". |
| `excess_kurtosis_threshold_ok` | 1,00 | Hair et al. "Multivariate Data Analysis". Heurística usada em SEM/CFA. Sem derivação teórica. **Ajustável.** |
| `excess_kurtosis_threshold_warn` | 2,00 | Idem. |

Caminho Shapiro-Wilk: usado quando `sample_size <= 5000`.
Caminho D'Agostino: usado quando `sample_size > 5000` e os campos `skewness`/`excess_kurtosis` estão presentes no Measurement descritivo. Se ausentes, nenhum Finding é emitido para aquela coluna.

#### `core.finding.missing_rate`

| Parâmetro | Valor | Origem |
|---|---|---|
| `warn_threshold` | 0,05 (5%) | Convenção prática. van Buuren "Flexible Imputation of Missing Data" usa 5% como ponto de decisão comum. Sem fundamentação teórica forte. **Ajustável.** |

A regra sempre emite, incluindo ok. O ok é evidência positiva de que a verificação passou.

Sentinelas de nulo aplicadas pelo plugin são registradas em `Finding.params["null_sentinels_applied"]` para tornar explícita a suposição sobre o que conta como ausente.

#### `core.finding.duplicate_rate`

| Parâmetro | Valor | Origem |
|---|---|---|
| `warn_threshold` | 0,01 (1%) | Convenção prática. Sem derivação teórica. **Ajustável.** |

Sempre emite, incluindo ok.

#### `core.finding.category_balance`

| Parâmetro | Valor | Origem |
|---|---|---|
| `warn_threshold` | 0,60 | Convenção prática. Uma classe cobrindo 60%+ sinaliza desequilíbrio moderado. Sem derivação teórica. **Ajustável.** |
| `fail_threshold` | 0,80 | Convenção prática. ~4:1 de razão; degrada a maioria dos classificadores sem reamostragem explícita. **Ajustável.** |
| `categorical_unique_rate_cutoff` | 0,05 | Heurística de detecção de coluna categórica: proporção de únicos ≤ 5%. **Ajustável.** |
| `categorical_unique_count_cutoff` | 20 | Heurística: contagem de únicos ≤ 20. **Ajustável.** |

A regra só emite para colunas identificadas como categóricas (heurística acima). Colunas não-categóricas não recebem Finding de balanceamento.

#### `core.finding.variable_association`

| Parâmetro | Valor | Origem |
|---|---|---|
| `emit_threshold` | 0,30 | Cohen (1988) "Statistical Power Analysis for the Behavioral Sciences", 2ª ed.: efeito médio = 0,3. Associações abaixo disso não são emitidas (não acionáveis). |
| `fail_threshold` | 0,70 | Convenção prática para risco de multicolinearidade. Extensão das categorias de Cohen (grande = 0,5); o limite específico 0,7 é convencional. **Ajustável.** |

Usa `|coefficient|` (tamanho de efeito), nunca `p_value`.

---

### Estrutura do sistema de regras (RuleRegistry)

`RULE_REGISTRY` em `core/rules/_registry.py` é análogo ao `SCHEMA_REGISTRY` de Measurements: singleton pré-populado na importação do pacote, sem estado mutável após inicialização.

- `FindingRule` e `AssessmentRule` são Protocols com `rule: str`, `rule_version: str`, e `evaluate()`.
- Regras são objetos stateless; nenhuma lê banco, chama modelo de linguagem ou produz I/O.
- Bump de `rule_version` é obrigatório para qualquer mudança de limiar que afete o veredito — isso altera o ID do Finding/Assessment, tornando a mudança rastreável no histórico.

### Dependência de objetivo em Assessments

O mesmo conjunto de Findings pode produzir Assessments diferentes para objetivos diferentes. Exemplo concreto implementado em `tests/test_rules.py::TestGoalDependency`:

- Finding `category_balance` com `severity=FAIL` → `modeling_readiness` = `not_eligible`
- O mesmo Finding → `data_quality` = inalterado (não considerado por essa regra)

`data_quality` considera apenas `missing_rate` e `duplicate_rate`. Desequilíbrio é uma característica da distribuição, não um defeito de qualidade — o mesmo dado pode ser alta qualidade e não adequado para modelagem sem reamostragem.

### Finding.params

Campo adicionado ao modelo `Finding` na Etapa 3. Contém os limiares efetivos usados pela regra para derivar o veredito. O ID do Finding inclui `params` na fórmula de hash — mudança de limiar produz ID diferente, tornando a decisão auditável e a mudança historicamente rastreável.

---

## 2026-07-25 — Etapa 4: Composer, Validator e geração de Claims

### Decisão: camada 3 (semântica) antecipada da Etapa 9 para a Etapa 4

A SPEC original colocava a camada 3 (verificação por LLM) na Etapa 9 e a Etapa 4 implementaria apenas camadas 1 e 2. A antecipação foi aprovada pelo seguinte motivo: a completude do validador é um invariante de segurança, não um incremento de funcionalidade. Implementar apenas L1+L2 entregaria um contrato falso — o validador pareceria completo mas permitiria que sentenças logicamente incorretas passassem silenciosamente. Ao entregar as três camadas juntas, o Claim passa a ter significado real desde o primeiro uso.

O comportamento de Etapa 9 passa a ser: ajuste fino das métricas de rejeição, calibração de prompts e análise empírica da taxa de rejeição por camada com datasets reais.

### Decisão: camada 2 verifica números contra Finding.params / Assessment.policy (não Measurements)

O validador numérico compara os números extraídos de cada sentença gerada contra os valores numéricos presentes em `Finding.params` e `Assessment.policy`, e nunca contra `Measurement.payload` diretamente.

**Motivo:** abrir um canal direto ao Measurement no caminho de validação permitiria que raw data do dataset chegasse ao processo de julgamento do texto, violando o princípio de isolamento do Composer. `Finding.params` já contém todos os números que a regra embute no `statement` — a coluna, a proporção, a contagem, os limiares.

**Contra-argumento tratado:** se uma regra copiar um número errado do Measurement para `Finding.params`, o validador não detectaria a divergência — ele compara a sentença com `Finding.params`, e ambos concordariam no valor errado. Para fechar esse buraco, foi adicionada uma garantia separada (ver próxima seção).

### Decisão: fidelidade Finding→Measurement verificada por suíte de testes parametrizados

`tests/test_statement_fidelity.py` contém uma classe de teste por regra de Finding que verifica, para um conjunto representativo de parâmetros, que todo número presente em `Finding.statement` é rastreável a `Finding.params` dentro da tolerância padrão (0,005). A ideia é que `Finding.params` deve espelhar fielmente os valores de `Measurement.payload` que a regra usou para gerar o statement.

A verificação é feita em tempo de teste (CI), não em runtime. Isso evita adicionar custo de asserção ao caminho quente de produção, enquanto garante que qualquer regressão de fidelidade quebre o build antes de chegar ao merge.

A função `extract_br_numbers` de `core/validation/_layer2.py` é reutilizada nesses testes para garantir que o mesmo parser que o validador usa seja o mesmo que audita a fidelidade.

### Decisão: Layer 2 usa formato numérico brasileiro para sentenças geradas por LLM

O Compositor gera texto em português (por instrução de prompt). Modelos de linguagem instruídos a escrever em português tendem a usar vírgula como separador decimal (ex: "7,6%"). `Finding.statement` usa formato Python padrão (ponto decimal, ex: "7.6%") porque é gerado deterministicamente por f-strings.

O parser de Layer 2 (`_BR_NUM_RE`) foi desenhado para o formato brasileiro. Para percentuais, o parser gera dois candidatos de comparação: o valor percentual (ex: 7.6) e a proporção correspondente (ex: 0.076). Qualquer um dos dois dentro da tolerância passa. Isso cobre tanto sentenças que citam "7,6%" quanto as raras que citam "0,076" sem sinal de percentual.

### Estrutura dos novos módulos (Etapa 4)

| Módulo | Responsabilidade |
|---|---|
| `core/llm.py` | `LanguageModel` Protocol + `StubLanguageModel` determinístico para testes |
| `core/validation/_layer1.py` | Verificação sintática: presença e validade de citações `[fnd-/ast-]` |
| `core/validation/_layer2.py` | Verificação numérica: parser BR + comparação contra params/policy |
| `core/validation/_layer3.py` | Verificação semântica: LLM juiz com contexto isolado |
| `core/validation/_validator.py` | Orquestração: para na primeira falha, expõe `RejectionRecord` e `ValidationMetrics` |
| `core/composer.py` | `generate_report()`: gera texto → divide em sentenças → valida → reescreve (até 2 tentativas) → produz Claims |
| `tests/test_composer.py` | Testa isolamento de assinatura + fluxo completo |
| `tests/test_validation.py` | Testa cada camada isoladamente + orquestração |
| `tests/test_statement_fidelity.py` | Garante fidelidade numérica Finding→Measurement por regra |

---

## 2026-07-27 — Etapa 5: três tabelas de run_membership em vez de uma

A SPEC descreve `run_membership(run_id, item_id, layer)` como uma associação genérica. Essa estrutura foi **intencionalmente substituída** por três tabelas separadas:

```sql
run_membership_measurements (run_id, measurement_id)
run_membership_findings     (run_id, finding_id)
run_membership_assessments  (run_id, assessment_id)
```

**Motivo:** uma única tabela com `item_id TEXT` genérico não pode declarar chaves estrangeiras reais para três tabelas-pai diferentes (`measurements`, `findings`, `assessments`). PostgreSQL não suporta FK polimórfica. Sem FKs, o banco não pode garantir a integridade referencial — um `item_id` poderia referenciar um registro inexistente sem que o banco detectasse. As três tabelas têm FKs reais e PRIMARY KEY composta `(run_id, item_id)` que combina unicidade e integridade em uma única declaração.

**Consequência para ON CONFLICT:** cada tabela usa `ON CONFLICT (run_id, measurement_id | finding_id | assessment_id) DO NOTHING`, que garante idempotência (re-executar o mesmo pipeline com o mesmo código e configuração é seguro).

**Assessment.scope não persistido:** o dataclass `Assessment` em `core/model.py` deliberadamente não inclui um campo `scope`. O scope é passado para `Assessment.create()` apenas para derivar o ID; uma vez derivado, o valor não é armazenado no objeto nem na tabela. A tabela `assessments` omite a coluna de scope por consequência direta dessa decisão do modelo.

---

## 2026-07-27 — Etapa 5: estrutura de módulos de persistência e API

| Módulo | Responsabilidade |
|---|---|
| `db/connection.py` | `get_connection()` — fábrica de conexão psycopg3 com `dict_row` |
| `db/migrations/` | Alembic: `env.py` lê `DATABASE_URL` do ambiente; `versions/0001_initial.py` cria todo o schema |
| `db/repos/` | Um arquivo por entidade: `upsert`, `get`, `list_*`. Sem ORM. |
| `db/repos/memberships.py` | Três funções `upsert_measurement/finding/assessment` para as tabelas de run_membership |
| `db/pipeline.py` | Orquestração: carrega dataset → roda capabilities baratas → aplica regras → persiste tudo → retorna `run_id` |
| `api/deps.py` | `get_db()` — dependency FastAPI que abre conexão psycopg3 e faz commit/rollback via context manager |
| `api/schemas.py` | Modelos Pydantic v2 para requests e responses |
| `api/routers/datasets.py` | `POST /datasets/upload`, `GET /datasets`, `GET /datasets/{id}`, `GET /datasets/{id}/runs` |
| `api/routers/runs.py` | `POST /runs`, `GET /runs/{id}`, `/measurements`, `/findings`, `/assessments`, `/claims`, `/validation`, `/metrics`, `/report` |
| `api/routers/catalog.py` | `GET /catalog` — catálogo de capabilities de todos os plugins registrados |
| `api/routers/chain.py` | `GET /chain/{item_id}` — cadeia de evidências a partir de qualquer item (`clm-`, `ast-`, `fnd-`, `msr-`) |
| `tests/conftest.py` | Fixture `db_conn`: conexão com `autocommit=False`, rollback no teardown |
| `tests/test_db.py` | Testes de repositório (requerem `TEST_DATABASE_URL`) |
| `tests/test_api.py` | Testes de endpoint (requerem `TEST_DATABASE_URL`) |

---

## 2026-07-29 — Etapa 6 Fatia 1: frontend — lista de datasets + laudo

### Stack

React + TypeScript + Vite + Tailwind CSS v4 (configurado via `@tailwindcss/vite`). Pasta `web/` na raiz. O Vite proxeia `/api/*` → `http://localhost:8000` em desenvolvimento — o frontend nunca fala com o banco diretamente.

### Identidade visual

| Elemento | Decisão |
|---|---|
| Tipografia de laudo (Claims) | Fraunces (Google Fonts) — serifada, ~18 px |
| Tipografia de interface | Inter (Google Fonts) — sans-serif |
| Identificadores e mono | JetBrains Mono |
| Tema padrão | escuro; alternância via botão no canto superior direito persistido em `localStorage` |
| Fundo escuro | `#101511`; texto `#E4EAE2`; divisórias `#1E2820`; muted `#647065` |
| Acento escuro | verde `#5FB98A` |
| Acento claro | verde `#2C6E49` |
| Badge FAIL | borda + texto `#E8756A`, fundo 12% |
| Badge WARN | borda + texto `#C48B2F` |
| Badge OK | borda + texto `#5FB98A` |

### Endpoint de laudo — `GET /runs/{run_id}/report`

Adicionado à Fatia 1 porque o frontend precisaria de lógica de negócio para agrupar Claims por seção e calcular severidade por Claim se essas computações ficassem no browser (violação da regra "sem lógica de negócio no frontend").

O endpoint retorna:
- `dataset_name`: primeiro `path` do manifest
- `counts.rows`: de `core.quality.missing` com scope `dataset`, campo `row_count`
- `counts.columns`: refs distintas de escopo `column` nos measurements desta run
- `counts.findings`: count de findings nesta run
- `counts.claims`: count de claims com `status = 'passed'`
- `sections`: Claims agrupados por `goal` do primeiro Assessment em `supports`; Claims que só suportam Findings vão para `goal = "general"`
- `severity` por Claim: max severity entre todos os Findings/Assessments em `supports`

Claims com `status = rejected_discarded` são excluídos na camada de repositório (`list_passed_by_run`) — nunca chegam ao endpoint de laudo.

### Organização de pastas do frontend

```
web/
  src/
    api/        # client.ts (fetch tipado) + types.ts (interfaces TS dos DTOs da API)
    components/ # SeverityBadge, ThemeToggle
    hooks/      # useTheme
    pages/      # DatasetList, Report
```

### Comandos para rodar tudo junto

```
# Terminal 1 — API (na raiz do repositório)
uv run uvicorn api.main:app --reload --port 8000

# Terminal 2 — Frontend (em web/)
npm run dev
```

Acesse `http://localhost:5173`. Para popular o banco, rode o pipeline antes de subir a interface.

---

## 2026-08-01 — Etapa 6 Fatia 2: gaveta de evidências

### Endpoint de cadeia — contrato

`GET /chain/{item_id}` — aceita prefixos `clm-`, `ast-`, `fnd-`, `msr-`. Retorna uma estrutura **plana** com quatro arrays paralelos:

```json
{
  "root_id": "clm-...",
  "claim": { "id", "text", "supports", "validation" } | null,
  "assessments": [ { "id", "goal", "verdict", "severity", "rule", "rule_version", "policy", "derived_from" } ],
  "findings":    [ { "id", "statement", "severity", "rule", "rule_version", "params", "derived_from" } ],
  "measurements":[ { "id", "type", "scope", "payload", "provenance": { "producer", "version", "params", "input_digest", "duration_ms", "seed" } } ]
}
```

A travessia acontece inteiramente no backend: o endpoint coleta todos os itens alcançáveis a partir do `item_id` raiz e os devolve em um único payload. O frontend nunca faz mais de um fetch por abertura de cadeia.

**Por que plano em vez de aninhado:** o frontend constrói a árvore para renderização cruzando IDs dentro do payload já recebido — isso é lógica de apresentação, não de negócio. Um payload plano é mais simples de serializar, testar e versionar.

### Comportamento do painel (EvidenceDrawer)

- Abre como drawer lateral deslizante da direita ao clicar em qualquer parte de um `ClaimRow` (texto, badge de severidade ou etiquetas de fonte).
- Largura: 480 px em telas ≥ 768 px; 100% em mobile. Overlay semi-transparente atrás fecha ao clicar.
- Cadeia sempre totalmente expandida — sem nível oculto. O `input_digest` e a procedência do Measurement aparecem inline sem clique adicional.
- Acessibilidade: `role="dialog"`, `aria-modal="true"`, foco move para o botão "×" na abertura, `Esc` fecha e retorna foco ao elemento que acionou o drawer.
- `prefers-reduced-motion`: respeitado globalmente via `index.css` (`transition-duration: 0.01ms !important`).

### Distinção visual das camadas

| Camada | Borda esquerda | Cor do chip de rótulo |
|---|---|---|
| Claim | nenhuma (cabeçalho do drawer) | `--color-text` |
| Assessment | 2 px `--color-accent` (verde) | `--color-accent` |
| Finding | 2 px `--color-muted` (cinza) | `--color-muted` |
| Measurement | 2 px `--color-divider` (sutil) | `--color-muted` |

Indentação progressiva com `pl-4` por nível. Provenance do Measurement em bloco bordeado `font-mono`.

### Arquivos de frontend criados/modificados

| Arquivo | Mudança |
|---|---|
| `web/src/api/types.ts` | Tipos adicionados: `ScopeOut`, `ProvenanceOut`, `MeasurementOut`, `FindingOut`, `AssessmentOut`, `EvidenceChain` |
| `web/src/api/client.ts` | `api.getChain(itemId)` — fetch único para `/chain/${itemId}` |
| `web/src/components/EvidenceDrawer.tsx` | Novo componente: drawer + renderização da árvore Claim → Assessment → Finding → Measurement |
| `web/src/pages/Report.tsx` | `ClaimRow` convertido para `<button>`, recebe `onOpenChain`; `Report` gerencia `selectedClaimId` e renderiza `EvidenceDrawer` |

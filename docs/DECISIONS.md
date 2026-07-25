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

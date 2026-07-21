# Prompt para o Claude Code

---

Você vai construir o MVP de uma plataforma de análise de datasets cuja característica definidora é esta:

**Nenhuma afirmação exibida ao usuário pode existir sem uma cadeia de evidências que chegue até o cálculo determinístico que a produziu.**

Esse princípio não é um requisito entre outros. Ele é a razão de existir do projeto e deve ser aplicado como restrição de tipo sempre que possível — se uma violação puder ser impedida pelo modelo de dados em vez de por convenção, impeça pelo modelo de dados.

Antes de escrever código, leia esta especificação inteira. Se algo aqui for ambíguo ou parecer errado, pergunte antes de implementar. Não invente requisitos que não estão aqui.

---

## 1. O modelo de quatro camadas

Toda informação no sistema pertence a exatamente uma das quatro camadas abaixo. Cada camada só pode derivar da anterior.

| Camada | Produzida por | Contém | Pode ser produzida por LLM? |
|---|---|---|---|
| **Measurement** | algoritmo determinístico | resultado numérico bruto, sem interpretação | Não |
| **Finding** | regra determinística versionada | interpretação local, verdadeira independentemente do objetivo do usuário | Não |
| **Assessment** | regra determinística versionada | decisão composta, condicionada a um objetivo declarado | Não |
| **Claim** | modelo de linguagem | frase em português para leitura humana | Sim, e somente esta |

A distinção entre Finding e Assessment é a seguinte, e deve ser respeitada com rigor:

- Um **Finding** é verdadeiro independentemente de quem pergunta. Ele descreve uma propriedade do dado.
- Um **Assessment** só faz sentido em relação a um objetivo (`goal`) declarado. A mesma configuração de Findings pode gerar Assessments diferentes para objetivos diferentes. Assessment é onde mora a política do sistema, e seus limiares devem ser configuráveis.

Existe ainda um quinto tipo, que **não** pertence à cadeia:

- **Artifact**: um render (especificação de gráfico, imagem, áudio). É consumido pelo humano no frontend, nunca pelo modelo de linguagem. O modelo pode referenciar um Artifact ("veja o gráfico X") mas nunca pode afirmar nada sobre o conteúdo visual dele.

**Regra que amarra o Artifact ao contrato:** toda operação que produz Artifact é obrigada a produzir também os Measurements correspondentes ao que aquele Artifact mostra. O core deve **rejeitar em runtime** um resultado que contenha artifacts e nenhum measurement. Escreva um teste para isso.

---

## 2. Modelo de dados

Implemente em `core/model.py` usando dataclasses congeladas (`frozen=True`) ou Pydantic com modelos imutáveis. Todos os IDs são determinísticos.

```python
class Layer(StrEnum):
    MEASUREMENT = "measurement"
    FINDING = "finding"
    ASSESSMENT = "assessment"
    CLAIM = "claim"

class Severity(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"

class ScopeKind(StrEnum):
    DATASET = "dataset"
    FILE = "file"
    COLUMN = "column"
    CHANNEL = "channel"
    SEGMENT = "segment"
    PAIR = "pair"

@dataclass(frozen=True)
class Scope:
    kind: ScopeKind
    ref: str | None          # identificador dentro do escopo, quando aplicável

@dataclass(frozen=True)
class Provenance:
    producer: str            # caminho totalmente qualificado do produtor
    version: str             # semver DO PRODUTOR, independente da versão da aplicação
    params: dict             # parâmetros efetivos usados, já resolvidos
    input_digest: str        # sha256 dos bytes exatos que entraram no cálculo
    duration_ms: int
    seed: int | None         # obrigatório quando o algoritmo for estocástico

@dataclass(frozen=True)
class Measurement:
    id: str
    dataset_id: str
    run_id: str
    type: str                # namespaced, ex: "core.stats.normality_test"
    scope: Scope
    payload: dict            # validado contra JSON Schema registrado para `type`
    provenance: Provenance

@dataclass(frozen=True)
class Finding:
    id: str
    dataset_id: str
    run_id: str
    type: str
    scope: Scope
    statement: str           # frase curta, escrita pela regra, NÃO por LLM
    severity: Severity
    derived_from: list[str]  # ids de Measurement — não vazio
    rule: str                # identificador da regra
    rule_version: str

@dataclass(frozen=True)
class Assessment:
    id: str
    dataset_id: str
    run_id: str
    type: str
    goal: str                # objetivo ao qual esta avaliação responde
    verdict: str
    severity: Severity
    derived_from: list[str]  # ids de Finding — não vazio
    rule: str
    rule_version: str
    policy: dict             # limiares efetivos usados, para auditoria

@dataclass(frozen=True)
class Claim:
    id: str
    dataset_id: str
    run_id: str
    text: str                # única string de texto livre gerada por LLM no sistema
    supports: list[str]      # ids de Assessment e/ou Finding — não vazio
    validation: ValidationRecord
```

### Determinismo do ID

O `id` de Measurement, Finding e Assessment é derivado por hash estável de `(dataset_id, type, scope, params_ou_policy, producer, version)` — **e não** de timestamp, contador ou UUID aleatório. Consequência pretendida: reexecutar o mesmo pipeline sobre o mesmo dataset com o mesmo código produz exatamente os mesmos IDs, o que torna dois relatórios comparáveis por diff. Escreva um teste que rode o pipeline duas vezes e afirme igualdade de todos os IDs.

### Persistência

PostgreSQL. Uma tabela por camada, `payload`/`policy` em `JSONB` com índice GIN. **Não crie tabela por domínio nem por tipo de measurement** — migrations por domínio inviabilizam o sistema de plugins. Referências entre camadas são arrays de texto com verificação de integridade na escrita.

---

## 3. O validador de Claims

Este é o componente mais importante do sistema. Implemente em `core/validation/` como três camadas independentes, executadas em ordem crescente de custo, com parada na primeira rejeição.

**Camada 1 — sintática.** Custo desprezível.
Toda sentença declarativa do texto gerado contém pelo menos uma referência; toda referência citada existe; toda referência pertence a este `run_id`.

**Camada 2 — numérica.** Determinística, é a que captura mais erro real.
Extraia todo número presente na sentença (aceite formatos com vírgula decimal e separador de milhar do português). Para cada número extraído, verifique se ele aparece — dentro de uma tolerância de arredondamento explícita e configurável — em algum dos Measurements alcançáveis a partir das referências citadas naquela sentença. Número sem lastro é rejeição. Trate corretamente percentuais, razões e valores arredondados para menos casas decimais.

**Camada 3 — semântica.** Uma chamada de modelo por sentença, cara.
Um segundo modelo recebe **apenas** a sentença isolada e **apenas** a serialização dos Findings/Assessments citados por ela. Não recebe o dataset, não recebe as outras sentenças, não recebe o resto do relatório. Esse isolamento é o que faz a checagem funcionar — não o simplifique. A saída é um enum: `entailed | unsupported | contradicted`. Apenas `entailed` passa.

**Fluxo de rejeição.** A sentença rejeitada volta ao redator com o motivo específico da rejeição anexado ao prompt. Após duas rejeições da mesma sentença, ela é descartada do laudo e registrada.

**Registro obrigatório.** Toda rejeição é persistida com: texto rejeitado, camada que rejeitou, motivo estruturado, tentativa. Esses registros são expostos na API e no frontend — eles não são log interno, são funcionalidade do produto.

**Métrica obrigatória.** O sistema calcula e expõe, por execução: total de sentenças geradas, taxa de rejeição por camada, número de sentenças descartadas.

---

## 4. Sistema de plugins

Interface mínima, em `core/plugin.py`. **Não adicione métodos além destes.** Se algo parecer precisar de um sexto método, pare e me pergunte.

```python
class DomainPlugin(Protocol):
    name: str
    version: str

    def sniff(self, source: Source) -> float:
        """Confiança de 0.0 a 1.0 de que este plugin sabe ler esta fonte,
        acompanhada de evidência textual do porquê."""

    def open(self, source: Source) -> Dataset: ...

    def catalog(self) -> Catalog:
        """Declara tudo que este plugin sabe produzir, sem executar nada."""

    def run(self, capability_id: str, ds: Dataset, **params) -> CapabilityResult: ...

    def reference_profiles(self) -> list[ProfileRef]: ...
```

```python
@dataclass(frozen=True)
class Capability:
    id: str
    description: str
    params_schema: dict       # JSON Schema dos parâmetros aceitos
    produces: list[str]       # tipos de Measurement que emite
    renders: bool             # produz Artifact?
    cost: Literal["cheap", "moderate", "expensive"]

@dataclass(frozen=True)
class Catalog:
    """Catálogo declarativo do que o domínio consegue produzir em cada camada."""
    capabilities: list[Capability]
    measurement_types: list[str]
    finding_rules: list[RuleRef]
    assessment_rules: list[RuleRef]

@dataclass(frozen=True)
class CapabilityResult:
    measurements: list[Measurement]
    artifacts: list[Artifact]
```

Restrições que o core deve impor:

- Um plugin **nunca** escreve no banco, **nunca** chama modelo de linguagem, **nunca** gera HTML.
- Descoberta de plugin via `entry_points` do `pyproject.toml`. Nada de registry próprio, hot reload ou sandbox.
- `CapabilityResult` com `artifacts` não vazio e `measurements` vazio é erro, levantado pelo core.

Implemente **dois** plugins neste MVP: um para dados tabulares e um para áudio. O de áudio existe para forçar a interface a suportar um domínio estruturalmente diferente do tabular; não o trate como opcional.

---

## 5. Ingestão

Implemente upload genérico de arquivos. O usuário envia um ou mais arquivos, ou um arquivo compactado contendo vários. O sistema não pede ao usuário que informe formato ou domínio.

Fluxo:

1. **Formato** é detectado automaticamente (magic bytes, extensão, inspeção de cabeçalho). Isso é determinístico e não precisa de confirmação.
2. **Domínio** é sugerido. Cada plugin registrado retorna uma confiança via `sniff()` acompanhada da evidência que a justifica. O sistema apresenta os candidatos ordenados por confiança e **exige confirmação do usuário** antes de prosseguir. Nunca escolha o domínio sozinho, mesmo com confiança alta — a sugestão errada contamina toda a cadeia abaixo dela.
3. A evidência da sugestão é exibida ao usuário em linguagem legível.

Arquivos maiores que a memória disponível devem ser lidos em blocos. Não carregue dataset inteiro em memória por padrão.

---

## 6. Pipeline

```
upload → detecção de formato → sugestão de domínio → confirmação do usuário
       → parsing → capabilities baratas executadas automaticamente
       → measurements → regras de finding → regras de assessment
       → redação de claims → validação → persistência
```

Regras:

- Na ingestão, execute automaticamente apenas capabilities de custo `cheap`. As demais ficam disponíveis sob demanda.
- Execução assíncrona com um único worker. Use `arq` ou `RQ`. **Não use Celery** e não construa arquitetura de filas múltiplas neste MVP.
- Cada execução do pipeline é um `run_id`. Execuções sobre o mesmo dataset são comparáveis entre si.

### Orçamento de sessão

Capabilities executadas sob demanda consomem um orçamento por sessão: tempo de CPU acumulado e número de execuções. O custo estimado de cada capability é declarado no catálogo antes de rodar. Ao esgotar o orçamento, o sistema recusa a execução e explica o motivo. Exponha o orçamento consumido na API.

---

## 7. Perguntas pré-respondidas

O pipeline responde automaticamente um conjunto fixo e pequeno de perguntas na ingestão. Cada pergunta é um `goal` que ativa um conjunto de regras de Assessment. Defina esse conjunto em configuração, não em código espalhado.

As perguntas são a porta de entrada da interface: o usuário chega e já encontra respostas prontas com veredito, podendo expandir cada uma até o cálculo. Uma caixa de pergunta livre existe abaixo delas, para o que não foi antecipado.

Quando uma pergunta livre não puder ser respondida pelos Measurements existentes, o sistema **recusa explicitamente** e oferece a capability que produziria a medição necessária. Nunca responda por inferência sem lastro. A recusa é comportamento correto, não falha.

---

## 8. Perfis de referência

Um perfil de referência é um artefato versionado contendo estatísticas agregadas de uma população conhecida, usado para comparação por métricas de drift (KS, PSI, Wasserstein).

Todo perfil carrega obrigatoriamente: fonte de derivação, licença da fonte, tamanho amostral, script de derivação versionado e digest. Perfil sem procedência completa não é carregado pelo sistema — é um erro de carga.

Neste MVP, implemente a mecânica de comparação e **um** perfil derivado de fonte pública com licença compatível. Não construa registry distribuído.

---

## 9. API e frontend

**API:** FastAPI. Endpoints para upload, listagem de datasets, execuções, catálogo de capabilities, execução sob demanda, consulta das quatro camadas, cadeia de evidências de um item qualquer, registros de validação e métricas de rejeição.

**Frontend:** React + TypeScript + Vite. Sem framework de UI pesado.

O backend emite especificações de gráfico (Vega-Lite JSON) e o frontend as renderiza. O backend **não** gera imagens. Isso torna todo gráfico serializável, versionável e testável.

Elementos obrigatórios da interface:

1. **Confirmação de domínio** com candidatos, confiança e evidência visível.
2. **Contagem de verificações** por severidade. **Não implemente um score agregado de qualidade** — um número único não é rastreável e viola o princípio do projeto.
3. **Linha do tempo de construção do conhecimento**: uma faixa mostrando quantos itens existem em cada camada, do Measurement ao Claim.
4. **Cartões de pergunta pré-respondida**, expansíveis.
5. **Gaveta de cadeia de evidências**: clicar em qualquer Claim abre a navegação Claim → Assessment → Finding → Measurement, exibindo em cada nível a regra e a versão que o produziu, e no nível final a procedência completa incluindo `input_digest`.
6. **Painel de validação** listando as sentenças rejeitadas, a camada que rejeitou e o motivo. Esta tela é funcionalidade visível, não ferramenta de depuração.

Distinga as camadas visualmente de forma consistente — o usuário deve reconhecer o nível de uma informação antes de ler o conteúdo.

Qualidade mínima não negociável: responsivo, foco de teclado visível, `prefers-reduced-motion` respeitado.

---

## 10. Testes

Além dos testes unitários por regra:

- **Determinismo de ID:** duas execuções idênticas produzem IDs idênticos.
- **Contrato Artifact/Measurement:** resultado com artifact e sem measurement é rejeitado.
- **Isolamento do redator:** teste que garanta que o componente que gera Claims recebe apenas Findings e Assessments serializados, e nunca dados brutos nem artifacts.
- **Validador numérico:** conjunto de sentenças com números adulterados que devem ser rejeitados, e sentenças corretas que devem passar.
- **Suíte de defeitos injetados:** gere programaticamente datasets com defeitos conhecidos e verifique quais o sistema detecta. Registre a taxa de detecção. Esta suíte é o principal ativo de evidência do projeto — trate-a como código de primeira classe.

---

## 11. O que NÃO construir neste MVP

Autenticação. Multi-tenancy. Registry distribuído de perfis. Marketplace de plugins. Hot reload. Sandbox de execução. Versionamento próprio de datasets. RAG sobre literatura. Agente autônomo. Kubernetes. Múltiplas filas. Score agregado de qualidade. Camadas de abstração DDD.

Se ao implementar algo você concluir que um destes itens é necessário, pare e me pergunte antes de construir.

---

## 12. Ordem de execução

Trabalhe nesta ordem e **pare ao final de cada etapa para eu revisar** antes de seguir para a próxima.

1. `core/model.py` com as quatro camadas, `Provenance`, `Artifact` e derivação determinística de ID. Mais os JSON Schemas de um conjunto inicial pequeno de tipos de Measurement. Testes de imutabilidade e determinismo.
2. Plugin tabular: `sniff`, `open`, `catalog`, capabilities baratas emitindo Measurements. Sem banco, sem API.
3. Regras de Finding e de Assessment, versionadas, com testes por regra.
4. Validador camadas 1 e 2, com testes. Primeiro laudo gerado e validado, saindo no terminal, sem frontend e sem banco.
5. Persistência em PostgreSQL e API FastAPI.
6. Frontend.
7. Plugin de áudio. Ao implementá-lo, relate onde a interface de plugin vazou ou precisou ser forçada — quero corrigir a abstração com base nisso antes de congelá-la.
8. Perfil de referência e comparação por drift.
9. Validador camada 3 e métricas de rejeição.
10. Suíte de defeitos injetados.

Ao final da etapa 4, o projeto está vivo. Tudo antes disso é fundação; tudo depois é superfície.

---

Comece pela etapa 1. Antes de escrever código, me mostre as decisões que você tomou sobre a derivação determinística de ID e sobre quais tipos de Measurement entram no conjunto inicial, e aguarde minha confirmação.

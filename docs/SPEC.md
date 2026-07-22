# Especificação — arquitetura e modelo de dados

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

Implemente em `core/model.py` usando dataclasses congeladas (`frozen=True`). Todos os IDs são determinísticos. Estruturas imutáveis — tentativa de mutação levanta exceção.

### Enumerações

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

class ArtifactKind(StrEnum):
    VEGA_LITE = "vega_lite"
    IMAGE = "image"
    AUDIO = "audio"

class ValidationLayer(StrEnum):
    SYNTACTIC = "syntactic"
    NUMERIC = "numeric"
    SEMANTIC = "semantic"

class ValidationVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"

class ValidationStatus(StrEnum):
    PASSED = "passed"
    REJECTED_DISCARDED = "rejected_discarded"
```

### Estruturas principais

```python
@dataclass(frozen=True)
class Scope:
    kind: ScopeKind
    refs: tuple[str, ...]   # PAIR exige dois referentes; para tipos simétricos,
                             # as refs são ordenadas canonicamente antes do hash
    # INVARIANTE: refs nunca é vazia para os ScopeKinds que exigem referentes.
    # A validação do tamanho mínimo fica no produtor, não no Scope.

@dataclass(frozen=True)
class Provenance:
    producer: str            # caminho totalmente qualificado do produtor
    version: str             # semver DO PRODUTOR
    params: Mapping[str, object]   # parâmetros efetivos; NaN e Infinity são
                                   # proibidos e rejeitados na construção
    input_digest: str        # sha256 dos bytes exatos que entraram no cálculo
    duration_ms: int
    seed: int | None         # obrigatório quando o algoritmo for estocástico

@dataclass(frozen=True)
class Measurement:
    id: str                  # prefixo msr-, veja Derivação de ID
    dataset_id: str
    type: str                # namespaced, ex: "core.stats.normality"
    scope: Scope
    payload: Mapping[str, object]   # validado contra JSON Schema registrado para `type`
    provenance: Provenance

@dataclass(frozen=True)
class Finding:
    id: str                  # prefixo fnd-
    dataset_id: str
    type: str
    scope: Scope
    statement: str           # frase curta, escrita pela regra, NÃO por LLM
    severity: Severity
    derived_from: tuple[str, ...]   # ids de Measurement (msr-) — não vazio
    rule: str
    rule_version: str

@dataclass(frozen=True)
class Assessment:
    id: str                  # prefixo ast-
    dataset_id: str
    type: str
    goal: str                # objetivo ao qual esta avaliação responde
    verdict: str
    severity: Severity
    derived_from: tuple[str, ...]   # ids de Finding (fnd-) — não vazio
    rule: str
    rule_version: str
    policy: Mapping[str, object]    # limiares efetivos usados, para auditoria

@dataclass(frozen=True)
class ValidationCheck:
    layer: ValidationLayer
    verdict: ValidationVerdict
    reason_code: str
    detail: Mapping[str, object]
    duration_ms: int

@dataclass(frozen=True)
class ValidationRecord:
    status: ValidationStatus
    attempts: int
    checks: tuple[ValidationCheck, ...]
    final_layer_reached: str

@dataclass(frozen=True)
class Claim:
    id: str                  # prefixo clm-, veja Derivação de ID
    dataset_id: str
    run_id: str              # Claim pertence a uma execução; Measurement/Finding/
                             # Assessment não — o pertencimento é run_membership
    text: str                # ÚNICA string de texto livre gerada por LLM no sistema
    supports: tuple[str, ...]  # ids de Assessment (ast-) e/ou Finding (fnd-) — não vazio
    validation: ValidationRecord

@dataclass(frozen=True)
class Artifact:
    id: str                  # prefixo art-, veja Derivação de ID
    dataset_id: str
    capability_id: str
    kind: ArtifactKind
    payload: Mapping[str, object]   # spec Vega-Lite, URI de imagem, etc.
    depicts: tuple[str, ...]  # ids de Measurement (msr-) — NÃO PODE SER VAZIO
    provenance: Provenance
```

### run_id e run_membership

`run_id` **não** aparece em Measurement, Finding nem Assessment. O pertencimento a uma execução é uma associação separada: `run_membership(run_id, item_id, layer)`. Isso garante que dois runs com o mesmo código sobre o mesmo dataset não produzam colisão de chave primária — os IDs de Measurement/Finding/Assessment são idempotentes por construção.

`Claim` mantém `run_id` porque é gerado dentro de uma execução e nunca é reutilizado entre runs.

### Enforcement de prefixo

Prefixo inválido em qualquer referência é rejeitado na construção com `ValueError`:

| Campo | Prefixos aceitos |
|---|---|
| `Finding.derived_from` | `msr-` |
| `Assessment.derived_from` | `fnd-` |
| `Claim.supports` | `fnd-` ou `ast-` |
| `Artifact.depicts` | `msr-` |

Consequência: referências circulares entre camadas são estruturalmente impossíveis.

---

## 3. Serialização canônica e derivação de ID

### Serialização canônica

Toda serialização usada para hash segue estas regras:

```python
json.dumps(obj, sort_keys=True, separators=(',', ':'),
           ensure_ascii=False, allow_nan=False)
```

Com pré-processamento obrigatório de todos os valores antes de serializar:

- `NaN` e `Infinity` → `ValueError` (rejeitados; indicam cálculo quebrado)
- `-0.0` → `0.0`
- `float` cujo valor é inteiro (ex: `1.0`) → `int` (ex: `1`)
- `dict` e `MappingProxyType` → processados recursivamente com `sort_keys`
- `list` e `tuple` → processados recursivamente como array JSON

**Teste-âncora obrigatório:** fixe a string canônica esperada de um dicionário de fixture e verifique bit a bit. Se a serialização mudar no futuro, o teste deve quebrar de forma explícita — não silenciosamente alterar todos os IDs.

### dataset_id

Derivado do conteúdo, nunca atribuído externamente. Algoritmo:

1. Para cada arquivo do dataset: calcule `sha256` dos bytes exatos.
2. Monte uma lista de `(caminho_relativo, sha256_do_arquivo)` ordenada pelo caminho.
3. Serialize canonicamente e calcule `sha256` da serialização.

```
dataset_id = "dset-" + sha256(canonical_json([
    {"path": p, "digest": d}
    for p, d in sorted_by_path
]))[:32]
```

Mesma coleção de arquivos, mesmo conteúdo → mesmo `dataset_id`. Qualquer mudança de conteúdo produz `dataset_id` diferente, o que garante que a decisão de excluir `input_digest` do hash de Measurement não cria falsos-positivos de igualdade.

### run_id

Determinístico: SHA-256 canônico de `(dataset_id, versões de todos os produtores registrados — dict ordenado por nome do produtor, digest da configuração efetiva)`. Prefixo `run-`.

```
run_id = "run-" + sha256(canonical_json({
    "dataset_id": dataset_id,
    "producers": {name: version, ...},   # ordenado por nome
    "config_digest": sha256_of_config,
}))[:32]
```

Reexecutar com mesmo código e configuração é idempotente. Mudar código ou configuração cria novo `run_id`, comparável por diff com o anterior.

### IDs de Measurement, Finding, Assessment

Fórmula geral: `sha256(canonical_json(identity_dict))[:32]`, prefixado pela camada.

**Measurement** — identidade lógica do cálculo:
```python
{
    "dataset_id": dataset_id,
    "type": type_,
    "scope": {"kind": scope.kind.value, "refs": list(scope.refs)},
    "params": dict(provenance.params),
    "producer": provenance.producer,
    "version": provenance.version,
}
```
Para tipos declarados como simétricos no JSON Schema (`"x-symmetric": true`), as `refs` são ordenadas canonicamente antes de entrar na identidade — `corr(a, b)` e `corr(b, a)` produzem o mesmo `id`.

**Finding** — identidade da regra aplicada:
```python
{
    "dataset_id": dataset_id,
    "type": type_,
    "scope": {"kind": scope.kind.value, "refs": list(scope.refs)},
    "params": {},
    "producer": rule,
    "version": rule_version,
}
```

**Assessment** — identidade da política aplicada ao objetivo:
```python
{
    "dataset_id": dataset_id,
    "type": type_,
    "scope": {"kind": scope.kind.value, "refs": list(scope.refs)},
    "goal": goal,
    "params": dict(policy),
    "producer": rule,
    "version": rule_version,
}
```

(`goal` está na fórmula de Assessment porque a mesma regra com a mesma política aplicada a goals distintos produz Assessments semanticamente distintos.)

### Claim.id

```
clm- + sha256(canonical_json({
    "run_id": run_id,
    "text": unicodedata.normalize("NFC", text.strip()),
    "supports": sorted(supports),
}))[:32]
```

Não é determinístico em relação à entrada do pipeline (o texto vem de LLM), mas é determinístico em relação à saída — retry com o mesmo texto produz o mesmo `id`.

### Artifact.id

```
art- + sha256(canonical_json({
    "dataset_id": dataset_id,
    "capability_id": capability_id,
    "params": dict(provenance.params),
    "producer": provenance.producer,
    "version": provenance.version,
}))[:32]
```

---

## 4. Registro de JSON Schemas para Measurement

Cada `type` de Measurement tem um JSON Schema registrado em arquivo versionado em `schemas/measurements/`. O `payload` é validado contra o schema no momento da construção de `Measurement`. Payload inválido ou tipo não registrado levanta exceção.

O campo `"x-symmetric": true` no schema declara que o tipo é simétrico (as refs de escopo são ordenadas antes do hash). Atualmente declarado para `core.stats.correlation`.

### Tipos iniciais

| Tipo | Área | Scope típico |
|---|---|---|
| `core.stats.descriptive` | Estatística descritiva | `COLUMN` |
| `core.stats.frequency` | Estatística descritiva | `COLUMN` |
| `core.quality.missing` | Qualidade de dados | `COLUMN` ou `DATASET` |
| `core.quality.uniqueness` | Qualidade de dados | `COLUMN` |
| `core.stats.normality` | Estatística descritiva | `COLUMN` |
| `core.stats.correlation` | Relação entre variáveis | `PAIR` |

---

## 5. O validador de Claims

Este é o componente mais importante do sistema. Implemente em `core/validation/` como três camadas independentes, executadas em ordem crescente de custo, com parada na primeira rejeição.

**Camada 1 — sintática.** Custo desprezível.
Toda sentença declarativa do texto gerado contém pelo menos uma referência; toda referência citada existe; toda referência pertence a este `run_id`.

**Camada 2 — numérica.** Determinística, é a que captura mais erro real.
Extraia todo número presente na sentença (aceite formatos com vírgula decimal e separador de milhar do português). Para cada número extraído, verifique se ele aparece — dentro de uma tolerância de arredondamento explícita e configurável — em algum dos Measurements alcançáveis a partir das referências citadas naquela sentença. Número sem lastro é rejeição. Trate corretamente percentuais, razões e valores arredondados para menos casas decimais.

**Camada 3 — semântica.** Uma chamada de modelo por sentença, cara.
Um segundo modelo recebe **apenas** a sentença isolada e **apenas** a serialização dos Findings/Assessments citados por ela. Não recebe o dataset, não recebe as outras sentenças, não recebe o resto do relatório. Esse isolamento é o que faz a checagem funcionar — não o simplifique. A saída é um enum: `entailed | unsupported | contradicted`. Apenas `entailed` passa.

**Fluxo de rejeição.** A sentença rejeitada volta ao redator com o motivo específico da rejeição anexado ao prompt. Após duas rejeições da mesma sentença, ela é descartada do laudo e registrada.

**Registro obrigatório.** Toda rejeição é persistida com: texto rejeitado, camada que rejeitou, motivo estruturado, tentativa. Esses registros são expostos na API e no frontend — eles não são log interno, são funcionalidade do produto.

Um Claim com `status = rejected_discarded` pode existir como registro persistido, mas **nunca** é exibido ao usuário. Essa fronteira é aplicada na serialização da API, não na camada de apresentação.

**Métrica obrigatória.** O sistema calcula e expõe, por execução: total de sentenças geradas, taxa de rejeição por camada, número de sentenças descartadas.

---

## 6. Sistema de plugins

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
    measurements: tuple[Measurement, ...]
    artifacts: tuple[Artifact, ...]
    # INVARIANTE: artifacts não-vazio com measurements vazio é erro de construção.
```

Restrições que o core deve impor:

- Um plugin **nunca** escreve no banco, **nunca** chama modelo de linguagem, **nunca** gera HTML.
- Descoberta de plugin via `entry_points` do `pyproject.toml`, grupo `data_observatory.plugins`. Nada de registry próprio, hot reload ou sandbox.
- `CapabilityResult` com `artifacts` não vazio e `measurements` vazio é erro, levantado pelo core na construção.

Implemente **dois** plugins neste MVP: um para dados tabulares e um para áudio. O de áudio existe para forçar a interface a suportar um domínio estruturalmente diferente do tabular; não o trate como opcional.

`Source`, `Dataset`, `RuleRef` e `ProfileRef` serão definidos na Etapa 2.

---

## 7. Ingestão

Implemente upload genérico de arquivos. O usuário envia um ou mais arquivos, ou um arquivo compactado contendo vários. O sistema não pede ao usuário que informe formato ou domínio.

Fluxo:

1. **Formato** é detectado automaticamente (magic bytes, extensão, inspeção de cabeçalho). Isso é determinístico e não precisa de confirmação.
2. **Domínio** é sugerido. Cada plugin registrado retorna uma confiança via `sniff()` acompanhada da evidência que a justifica. O sistema apresenta os candidatos ordenados por confiança e **exige confirmação do usuário** antes de prosseguir. Nunca escolha o domínio sozinho, mesmo com confiança alta — a sugestão errada contamina toda a cadeia abaixo dela.
3. A evidência da sugestão é exibida ao usuário em linguagem legível.

Arquivos maiores que a memória disponível devem ser lidos em blocos. Não carregue dataset inteiro em memória por padrão.

---

## 8. Pipeline

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

## 9. Perguntas pré-respondidas

O pipeline responde automaticamente um conjunto fixo e pequeno de perguntas na ingestão. Cada pergunta é um `goal` que ativa um conjunto de regras de Assessment. Defina esse conjunto em configuração, não em código espalhado.

As perguntas são a porta de entrada da interface: o usuário chega e já encontra respostas prontas com veredito, podendo expandir cada uma até o cálculo. Uma caixa de pergunta livre existe abaixo delas, para o que não foi antecipado.

Quando uma pergunta livre não puder ser respondida pelos Measurements existentes, o sistema **recusa explicitamente** e oferece a capability que produziria a medição necessária. Nunca responda por inferência sem lastro. A recusa é comportamento correto, não falha.

---

## 10. Perfis de referência

Um perfil de referência é um artefato versionado contendo estatísticas agregadas de uma população conhecida, usado para comparação por métricas de drift (KS, PSI, Wasserstein).

Todo perfil carrega obrigatoriamente: fonte de derivação, licença da fonte, tamanho amostral, script de derivação versionado e digest. Perfil sem procedência completa não é carregado pelo sistema — é um erro de carga.

Neste MVP, implemente a mecânica de comparação e **um** perfil derivado de fonte pública com licença compatível. Não construa registry distribuído.

---

## 11. API e frontend

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

## 12. Testes

Além dos testes unitários por regra:

- **Determinismo de ID:** duas execuções idênticas produzem IDs idênticos.
- **Contrato Artifact/Measurement:** resultado com artifact e sem measurement é rejeitado.
- **Isolamento do redator:** teste que garanta que o componente que gera Claims recebe apenas Findings e Assessments serializados, e nunca dados brutos nem artifacts.
- **Validador numérico:** conjunto de sentenças com números adulterados que devem ser rejeitados, e sentenças corretas que devem passar.
- **Suíte de defeitos injetados:** gere programaticamente datasets com defeitos conhecidos e verifique quais o sistema detecta. Registre a taxa de detecção. Esta suíte é o principal ativo de evidência do projeto — trate-a como código de primeira classe.

---

## 13. O que NÃO construir neste MVP

Autenticação. Multi-tenancy. Registry distribuído de perfis. Marketplace de plugins. Hot reload. Sandbox de execução. Versionamento próprio de datasets. RAG sobre literatura. Agente autônomo. Kubernetes. Múltiplas filas. Score agregado de qualidade. Camadas de abstração DDD.

Se ao implementar algo você concluir que um destes itens é necessário, pare e me pergunte antes de construir.

---

## 14. Ordem de execução

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

# provenance

[Read in English](README.md)

Ferramentas de IA conseguem ler uma planilha, escrever um relatório e soar completamente confiantes — mesmo quando os números estão errados. O modelo não sabe que está alucinando; ele não tem noção de verdade, apenas de palavras plausíveis. Quem lê o relatório não tem como verificar, porque não existe nenhuma trilha a seguir.

O provenance trata cada afirmação feita por um modelo de linguagem como algo que precisa ser provado, não apenas declarado. Pense num jornalista que não só conta o que aconteceu mas entrega o documento original. Cada número exibido ao usuário deve ser rastreável, passo a passo, até o cálculo determinístico que o produziu — measurements, regras, decisões, tudo registrado e navegável.

## Modelo de quatro camadas

| Camada | Produzida por | Contém | Pode ser produzida por LLM? |
|---|---|---|---|
| **Measurement** | algoritmo determinístico | resultado numérico bruto, sem interpretação | Não |
| **Finding** | regra determinística versionada | interpretação local, verdadeira independentemente do objetivo do usuário | Não |
| **Assessment** | regra determinística versionada | decisão composta, condicionada a um objetivo declarado | Não |
| **Claim** | modelo de linguagem | frase em português para leitura humana | Sim, e somente esta |

As três primeiras camadas são totalmente determinísticas e auditáveis. A camada numérica captura a maioria das alucinações na prática, pois modelos de linguagem erram principalmente em números. Apenas a camada Claim é gerada por LLM — e ela só pode descrever o que as camadas abaixo já provaram.

## Estrutura do projeto

```
provenance/
├── api/            # FastAPI — main.py, routers/, deps.py, schemas.py
├── core/           # Modelo de domínio — model, composer, plugin, rules/, validation/
├── db/             # Persistência — connection, pipeline, migrations/, repos/
├── docs/           # SPEC.md, DECISIONS.md
├── plugins/
│   └── tabular/    # Plugin CSV/Parquet (_digest, _plugin, _stats)
├── schemas/        # Schemas JSON das measurements
├── scripts/        # Scripts utilitários e demonstração
├── tests/          # Suíte de testes (358 casos)
└── web/            # Frontend React/Vite
    └── src/        # App.tsx, pages/, components/, hooks/, api/
```

## Versões

| Componente | Versão |
|---|---|
| Python | ≥ 3.12 (testado em 3.13) |
| PostgreSQL | 16 |
| pyarrow | 18.1.0 |
| scipy | 1.18.0 |
| FastAPI | 0.140.7 |
| SQLAlchemy | 2.0.51 |
| Alembic | 1.18.5 |
| React | 19.2.7 |
| TypeScript | 6.0.x |
| Vite | 8.1.1 |

## Testes

358 casos distribuídos em 8 arquivos, cobrindo `core`, `plugins`, `db` e `api`:

| Arquivo | Casos | O que cobre |
|---|---|---|
| `test_tabular.py` | 100 | plugin CSV/Parquet (property-based via Hypothesis) |
| `test_rules.py` | 74 | regras de interpretação (Finding e Assessment) |
| `test_model.py` | 68 | modelo de domínio (Measurement → Claim) |
| `test_validation.py` | 48 | validação e composição de cadeia |
| `test_statement_fidelity.py` | 23 | fidelidade semântica dos Claims |
| `test_composer.py` | 22 | composição da cadeia de evidências |
| `test_api.py` | 12 | REST API (FastAPI + httpx) |
| `test_db.py` | 10 | camada de persistência (psycopg3 + Alembic) |

## Configuração local

### Pré-requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — gerenciador de pacotes
- PostgreSQL 16 instalado localmente
- Node.js 20+ (para o frontend)

### Instalando o PostgreSQL 16 no Windows

1. Baixe o instalador em <https://www.postgresql.org/download/windows/> (EDB installer).
2. Execute o instalador. Quando pedir senha do usuário `postgres`, anote a senha escolhida.
3. Confirme que o serviço está rodando: abra o **Gerenciador de Serviços** (`services.msc`) e procure `postgresql-x64-16`. O status deve ser **Em execução**.
4. Opcionalmente, adicione `C:\Program Files\PostgreSQL\16\bin` ao PATH do sistema.

### Criando os bancos de dados

Abra o **SQL Shell (psql)** ou o pgAdmin e execute:

```sql
CREATE DATABASE provenance;
CREATE DATABASE provenance_test;
```

### Configuração do ambiente

```bash
cp .env.example .env
```

Edite `.env` ajustando a senha do `postgres`:

```
DATABASE_URL=postgresql://postgres:SUA_SENHA@localhost:5432/provenance
TEST_DATABASE_URL=postgresql://postgres:SUA_SENHA@localhost:5432/provenance_test
```

### Instalação

```bash
uv sync
```

### Migrations

```bash
# Banco principal
uv run alembic upgrade head

# Banco de testes
uv run alembic -x url=postgresql://postgres:SUA_SENHA@localhost:5432/provenance_test upgrade head
```

### API

```bash
uv run uvicorn api.main:app --reload
```

Disponível em <http://localhost:8000> — documentação interativa em <http://localhost:8000/docs>.

### Frontend

```bash
cd web
npm install
npm run dev
```

Disponível em <http://localhost:5173>.

### Testes

```bash
uv run pytest
```

Com `.env` presente e `TEST_DATABASE_URL` configurado, todos os 358 testes são executados (incluindo os de banco e API). Sem ele, os testes que dependem do banco são pulados automaticamente.

## Desenvolvimento

```bash
uv run ruff format .                      # formata o código
uv run ruff check .                       # linting
uv run python -m mypy core db api tests   # verificação de tipos
uv run pytest                             # suíte completa
```

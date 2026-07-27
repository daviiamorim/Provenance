# data-observatory

## Princípio

Nenhuma afirmação exibida ao usuário pode existir sem uma cadeia de evidências que chegue até o cálculo determinístico que a produziu.

## Modelo de quatro camadas

| Camada | Produzida por | Contém | Pode ser produzida por LLM? |
|---|---|---|---|
| **Measurement** | algoritmo determinístico | resultado numérico bruto, sem interpretação | Não |
| **Finding** | regra determinística versionada | interpretação local, verdadeira independentemente do objetivo do usuário | Não |
| **Assessment** | regra determinística versionada | decisão composta, condicionada a um objetivo declarado | Não |
| **Claim** | modelo de linguagem | frase em português para leitura humana | Sim, e somente esta |

## Configuração local

### Pré-requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — gerenciador de pacotes
- PostgreSQL 16 instalado localmente

### Instalando o PostgreSQL 16 no Windows

1. Baixe o instalador em <https://www.postgresql.org/download/windows/> (EDB installer).
2. Execute o instalador. Quando pedir senha do usuário `postgres`, escolha uma senha e anote — você vai precisar dela.
3. Confirme que o serviço está rodando: abra o **Gerenciador de Serviços** (services.msc) e procure `postgresql-x64-16`. O status deve ser **Em execução**.
4. Opcionalmente, adicione `C:\Program Files\PostgreSQL\16\bin` ao PATH do sistema para usar `psql` no terminal.

### Criando os bancos de dados

Abra o **SQL Shell (psql)** — ou o pgAdmin — e execute:

```sql
CREATE DATABASE data_observatory;
CREATE DATABASE data_observatory_test;
```

### Configuração do ambiente

```bash
cp .env.example .env
```

Edite `.env` se necessário (ajuste a senha do `postgres`):

```
DATABASE_URL=postgresql://postgres:SUA_SENHA@localhost:5432/data_observatory
TEST_DATABASE_URL=postgresql://postgres:SUA_SENHA@localhost:5432/data_observatory_test
```

### Instalando dependências e rodando as migrations

```bash
uv sync

# Banco principal
uv run alembic upgrade head

# Banco de testes
uv run alembic -x url=postgresql://postgres:SENHA@localhost:5432/data_observatory_test upgrade head
```

Substitua `SENHA` pela senha do usuário `postgres` escolhida durante a instalação. Se usou `postgres` (padrão), o comando fica:

```bash
uv run alembic upgrade head
uv run alembic -x url=postgresql://postgres:postgres@localhost:5432/data_observatory_test upgrade head
```

### Rodando os testes

```bash
uv run pytest
```

Se o arquivo `.env` existir no diretório do projeto, ele é carregado automaticamente pelo `conftest.py`. Com `TEST_DATABASE_URL` disponível, todos os 357 testes (incluindo 22 de banco/API) são executados. Sem ele, os testes de banco são pulados graciosamente.

### Rodando o servidor da API

```bash
uv run uvicorn api.main:app --reload
```

A API fica disponível em <http://localhost:8000>. Documentação interativa em <http://localhost:8000/docs>.

## Estrutura do projeto

```
core/           — modelo de dados (Measurement → Finding → Assessment → Claim)
plugins/        — plugins de domínio (tabular: CSV + Parquet)
db/             — camada de persistência (psycopg3, Alembic, repositórios)
api/            — REST API (FastAPI)
tests/          — suíte de testes (pytest + hypothesis)
docs/           — decisões de design (DECISIONS.md)
scripts/        — utilitários e demonstração (demo.py)
```

## Desenvolvimento

```bash
uv run ruff format .       # formata o código
uv run ruff check .        # linting
uv run mypy core db api tests  # verificação de tipos
uv run pytest              # suíte completa
```

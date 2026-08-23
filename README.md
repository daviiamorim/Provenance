# provenance

[Leia em português](README.pt.md)

AI tools can read a spreadsheet, write a report, and sound completely confident — even when the numbers are wrong. The model doesn't know it's hallucinating; it has no concept of truth, only of plausible next words. The person reading the report has no way to check, because there's no trail to follow.

provenance treats every claim a language model makes as something that must be proven, not asserted. Think of a journalist who doesn't just tell you what happened but hands you the original document. Every number shown to a user traces back, step by step, to the exact deterministic calculation that produced it — measurements, rules, decisions, all recorded and navigable.

## Four-layer model

| Layer | Produced by | Contains | Can an LLM produce it? |
|---|---|---|---|
| **Measurement** | deterministic algorithm | raw numeric result, no interpretation | No |
| **Finding** | versioned deterministic rule | local interpretation, true regardless of user objective | No |
| **Assessment** | versioned deterministic rule | composite decision, conditioned on a declared objective | No |
| **Claim** | language model | human-readable sentence | Yes, and only this |

The first three layers are fully deterministic and auditable. The numeric layer catches the most hallucinations in practice, since language models err mainly on numbers. Only the Claim layer is LLM-generated — and it can only describe what the layers below have already proven.

## Project structure

```
provenance/
├── api/            # FastAPI — main.py, routers/, deps.py, schemas.py
├── core/           # Domain model — model, composer, plugin, rules/, validation/
├── db/             # Persistence — connection, pipeline, migrations/, repos/
├── docs/           # SPEC.md, DECISIONS.md
├── plugins/
│   └── tabular/    # CSV/Parquet plugin (_digest, _plugin, _stats)
├── schemas/        # Measurement JSON schemas
├── scripts/        # Utility scripts and demo
├── tests/          # Test suite (358 cases)
└── web/            # React/Vite frontend
    └── src/        # App.tsx, pages/, components/, hooks/, api/
```

## Versions

| Component | Version |
|---|---|
| Python | ≥ 3.12 (tested on 3.13) |
| PostgreSQL | 16 |
| pyarrow | 18.1.0 |
| scipy | 1.18.0 |
| FastAPI | 0.140.7 |
| SQLAlchemy | 2.0.51 |
| Alembic | 1.18.5 |
| React | 19.2.7 |
| TypeScript | 6.0.x |
| Vite | 8.1.1 |

## Tests

358 cases across 8 files, covering `core`, `plugins`, `db`, and `api`:

| File | Cases | What it covers |
|---|---|---|
| `test_tabular.py` | 100 | CSV/Parquet plugin (property-based via Hypothesis) |
| `test_rules.py` | 74 | interpretation rules (Finding and Assessment) |
| `test_model.py` | 68 | domain model (Measurement → Claim) |
| `test_validation.py` | 48 | chain validation and composition |
| `test_statement_fidelity.py` | 23 | Claim semantic fidelity |
| `test_composer.py` | 22 | evidence chain composition |
| `test_api.py` | 12 | REST API (FastAPI + httpx) |
| `test_db.py` | 10 | persistence layer (psycopg3 + Alembic) |

## Local setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — package manager
- PostgreSQL 16 installed locally
- Node.js 20+ (for the frontend)

### Installing PostgreSQL 16 on Windows

1. Download the installer at <https://www.postgresql.org/download/windows/> (EDB installer).
2. Run the installer. When prompted for the `postgres` user password, note it down.
3. Confirm the service is running: open **Services** (`services.msc`) and find `postgresql-x64-16`. Status should be **Running**.
4. Optionally, add `C:\Program Files\PostgreSQL\16\bin` to the system PATH.

### Creating the databases

Open **SQL Shell (psql)** or pgAdmin and run:

```sql
CREATE DATABASE provenance;
CREATE DATABASE provenance_test;
```

### Environment setup

```bash
cp .env.example .env
```

Edit `.env` to set your `postgres` password:

```
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/provenance
TEST_DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/provenance_test
```

### Installation

```bash
uv sync
```

### Migrations

```bash
# Main database
uv run alembic upgrade head

# Test database
uv run alembic -x url=postgresql://postgres:YOUR_PASSWORD@localhost:5432/provenance_test upgrade head
```

### API

```bash
uv run uvicorn api.main:app --reload
```

Available at <http://localhost:8000> — interactive docs at <http://localhost:8000/docs>.

### Frontend

```bash
cd web
npm install
npm run dev
```

Available at <http://localhost:5173>.

### Tests

```bash
uv run pytest
```

With `.env` present and `TEST_DATABASE_URL` set, all 358 tests run (including database and API tests). Without it, database-dependent tests are skipped automatically.

## Development

```bash
uv run ruff format .                      # format
uv run ruff check .                       # lint
uv run python -m mypy core db api tests   # type check
uv run pytest                             # full suite
```

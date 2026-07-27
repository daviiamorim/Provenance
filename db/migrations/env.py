"""Alembic migration environment — reads DATABASE_URL from env or .env file."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

# Load .env from project root if present — setdefault so explicit env vars win.
_env_file = Path(__file__).parent.parent.parent / ".env"
if _env_file.exists():
    for _raw in _env_file.read_text(encoding="utf-8").splitlines():
        _raw = _raw.strip()
        if _raw and not _raw.startswith("#") and "=" in _raw:
            _k, _, _v = _raw.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# -x url=... overrides DATABASE_URL (useful for running against the test DB).
_x_args: dict[str, str] = context.get_x_argument(as_dictionary=True)  # type: ignore[assignment]
_raw_url = _x_args.get("url") or os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/data_observatory"
)
# Alembic needs the SQLAlchemy dialect prefix for psycopg3.
_sa_url = _raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
config.set_main_option("sqlalchemy.url", _sa_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

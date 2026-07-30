"""FastAPI application entry point."""

from __future__ import annotations

# Load .env before any module reads os.environ at import time.
# python-dotenv is a no-op when the vars are already set (e.g., in CI).
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI  # noqa: E402

from api.routers import catalog, chain, datasets, runs  # noqa: E402

app = FastAPI(
    title="data-observatory",
    description="Evidence-chain analytics platform — every claim is traceable.",
    version="0.1.0",
)

app.include_router(datasets.router)
app.include_router(runs.router)
app.include_router(catalog.router)
app.include_router(chain.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

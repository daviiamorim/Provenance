"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from api.routers import catalog, chain, datasets, runs

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

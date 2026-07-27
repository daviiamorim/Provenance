"""Dataset endpoints: upload and list."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, UploadFile

from api.deps import get_db
from api.schemas import DatasetOut, DomainCandidate, RunOut, UploadOut
from core.model import derive_dataset_id
from core.plugin import Source
from db.repos import datasets as dataset_repo
from db.repos import runs as run_repo
from plugins.tabular import TabularPlugin

router = APIRouter(prefix="/datasets", tags=["datasets"])

Conn = psycopg.Connection[dict[str, Any]]


def _sniff_candidates(source: Source) -> list[DomainCandidate]:
    candidates: list[DomainCandidate] = []
    plugin = TabularPlugin()
    result = plugin.sniff(source)
    if result.confidence > 0:
        candidates.append(
            DomainCandidate(
                plugin_name=plugin.name,
                confidence=result.confidence,
                evidence=result.evidence,
            )
        )
    return sorted(candidates, key=lambda c: c.confidence, reverse=True)


@router.post("/upload", response_model=UploadOut, status_code=201)
async def upload_dataset(
    files: list[UploadFile],
    conn: Annotated[Conn, Depends(get_db)],
) -> UploadOut:
    """Upload one or more files. Returns dataset_id and domain candidates.

    The caller should then POST /runs with the chosen plugin to start analysis.
    """
    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required")

    upload_dir = Path(tempfile.mkdtemp(prefix="dobs_"))
    saved_paths: list[Path] = []
    for file in files:
        filename = file.filename or "upload"
        dest = upload_dir / Path(filename).name
        content = await file.read()
        dest.write_bytes(content)
        saved_paths.append(dest)

    source = Source(paths=tuple(saved_paths))

    manifest: list[dict[str, str]] = []
    for p in saved_paths:
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        manifest.append({"path": p.name, "digest": digest})

    dataset_id = derive_dataset_id(
        [(item["path"], item["digest"]) for item in manifest]
    )
    dataset_repo.upsert(conn, dataset_id, manifest, str(upload_dir))

    candidates = _sniff_candidates(source)
    return UploadOut(dataset_id=dataset_id, candidates=candidates)


@router.get("", response_model=list[DatasetOut])
def list_datasets(conn: Annotated[Conn, Depends(get_db)]) -> list[DatasetOut]:
    rows = dataset_repo.list_all(conn)
    return [
        DatasetOut(
            id=str(r["id"]),
            created_at=r["created_at"],
            manifest=list(r["manifest"]),
        )
        for r in rows
    ]


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    dataset_id: str,
    conn: Annotated[Conn, Depends(get_db)],
) -> DatasetOut:
    row = dataset_repo.get(conn, dataset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return DatasetOut(
        id=str(row["id"]),
        created_at=row["created_at"],
        manifest=list(row["manifest"]),
    )


@router.get("/{dataset_id}/runs", response_model=list[RunOut])
def list_runs_for_dataset(
    dataset_id: str,
    conn: Annotated[Conn, Depends(get_db)],
) -> list[RunOut]:
    if dataset_repo.get(conn, dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    rows = run_repo.list_by_dataset(conn, dataset_id)
    return [
        RunOut(
            id=str(r["id"]),
            dataset_id=str(r["dataset_id"]),
            producer_versions=dict(r["producer_versions"]),
            config_digest=str(r["config_digest"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]

"""FastAPI endpoint tests — require TEST_DATABASE_URL (skipped otherwise).

Each test shares the db_conn fixture (BEGIN/ROLLBACK isolation) and overrides
the get_db dependency so the API routes operate on the same rolled-back
connection.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Generator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from api.deps import get_db
from api.main import app


@pytest.fixture
def client(
    db_conn: psycopg.Connection[dict[str, Any]],
) -> Generator[TestClient, None, None]:
    def _override() -> Generator[psycopg.Connection[dict[str, Any]], None, None]:
        yield db_conn

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def simple_csv_bytes() -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["name", "age", "score"])
    writer.writerow(["Alice", "30", "0.95"])
    writer.writerow(["Bob", "25", "0.87"])
    writer.writerow(["Carol", "35", "0.92"])
    return buf.getvalue().encode()


# ── health ────────────────────────────────────────────────────────────────────


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── catalog ───────────────────────────────────────────────────────────────────


def test_catalog(client: TestClient) -> None:
    r = client.get("/catalog")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert items[0]["plugin_name"] == "tabular"
    caps = {c["id"] for c in items[0]["capabilities"]}
    assert "tabular.column.missing" in caps


# ── upload + run ──────────────────────────────────────────────────────────────


def test_upload_dataset(client: TestClient, simple_csv_bytes: bytes) -> None:
    r = client.post(
        "/datasets/upload",
        files=[("files", ("test.csv", simple_csv_bytes, "text/csv"))],
    )
    assert r.status_code == 201
    body = r.json()
    assert body["dataset_id"].startswith("dset-")
    assert len(body["candidates"]) >= 1
    assert body["candidates"][0]["plugin_name"] == "tabular"
    assert body["candidates"][0]["confidence"] > 0.5


def test_upload_no_files(client: TestClient) -> None:
    r = client.post("/datasets/upload", files=[])
    assert r.status_code == 422


def test_list_datasets_empty(client: TestClient) -> None:
    r = client.get("/datasets")
    assert r.status_code == 200
    assert r.json() == []


def test_get_dataset_not_found(client: TestClient) -> None:
    r = client.get("/datasets/dset-notexist")
    assert r.status_code == 404


def test_full_pipeline(client: TestClient, simple_csv_bytes: bytes) -> None:
    # 1. upload
    r = client.post(
        "/datasets/upload",
        files=[("files", ("data.csv", simple_csv_bytes, "text/csv"))],
    )
    assert r.status_code == 201
    dataset_id = r.json()["dataset_id"]

    # 2. create run (confirms domain + executes pipeline)
    r = client.post(
        "/runs",
        json={
            "dataset_id": dataset_id,
            "plugin_name": "tabular",
            "goals": ["data_quality", "modeling_readiness"],
        },
    )
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    assert run_id.startswith("run-")

    # 3. query results
    r = client.get(f"/runs/{run_id}/measurements")
    assert r.status_code == 200
    msrs = r.json()
    assert len(msrs) > 0
    types_found = {m["type"] for m in msrs}
    assert "core.quality.missing" in types_found

    r = client.get(f"/runs/{run_id}/findings")
    assert r.status_code == 200
    assert len(r.json()) > 0

    r = client.get(f"/runs/{run_id}/assessments")
    assert r.status_code == 200
    assert len(r.json()) > 0

    # 4. idempotency: same inputs → same run_id
    r2 = client.post(
        "/runs",
        json={"dataset_id": dataset_id, "plugin_name": "tabular"},
    )
    assert r2.status_code == 201
    assert r2.json()["run_id"] == run_id


def test_evidence_chain_for_measurement(
    client: TestClient, simple_csv_bytes: bytes
) -> None:
    r = client.post(
        "/datasets/upload",
        files=[("files", ("data.csv", simple_csv_bytes, "text/csv"))],
    )
    dataset_id = r.json()["dataset_id"]
    r = client.post("/runs", json={"dataset_id": dataset_id})
    run_id = r.json()["run_id"]

    msrs = client.get(f"/runs/{run_id}/measurements").json()
    msr_id = msrs[0]["id"]

    r = client.get(f"/chain/{msr_id}")
    assert r.status_code == 200
    chain = r.json()
    assert chain["root_id"] == msr_id
    assert len(chain["measurements"]) == 1
    assert chain["claim"] is None


def test_evidence_chain_for_finding(
    client: TestClient, simple_csv_bytes: bytes
) -> None:
    r = client.post(
        "/datasets/upload",
        files=[("files", ("data.csv", simple_csv_bytes, "text/csv"))],
    )
    dataset_id = r.json()["dataset_id"]
    client.post("/runs", json={"dataset_id": dataset_id})
    runs = client.get(f"/datasets/{dataset_id}/runs").json()
    run_id = runs[0]["id"]

    findings = client.get(f"/runs/{run_id}/findings").json()
    fnd_id = findings[0]["id"]

    r = client.get(f"/chain/{fnd_id}")
    assert r.status_code == 200
    chain = r.json()
    assert chain["root_id"] == fnd_id
    assert len(chain["findings"]) == 1
    assert len(chain["measurements"]) > 0


def test_run_metrics_no_claims(client: TestClient, simple_csv_bytes: bytes) -> None:
    r = client.post(
        "/datasets/upload",
        files=[("files", ("data.csv", simple_csv_bytes, "text/csv"))],
    )
    dataset_id = r.json()["dataset_id"]
    r = client.post("/runs", json={"dataset_id": dataset_id})
    run_id = r.json()["run_id"]

    r = client.get(f"/runs/{run_id}/metrics")
    assert r.status_code == 200
    m = r.json()
    assert m["run_id"] == run_id
    assert m["total_claims"] == 0
    assert m["total_passed"] == 0


def test_run_not_found(client: TestClient) -> None:
    r = client.get("/runs/run-notexist")
    assert r.status_code == 404


def test_chain_unknown_prefix(client: TestClient) -> None:
    r = client.get("/chain/xxx-badprefix")
    assert r.status_code == 422

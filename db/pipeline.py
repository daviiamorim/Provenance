"""Pipeline orchestration: cheap capabilities → findings → assessments → persist.

Called by the API after the user confirms the domain plugin. Returns run_id.
No I/O or LLM calls happen here; Claims are generated separately by the
Composer (core/composer.py) and persisted via db.repos.claims.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from core.model import Assessment, Finding, Measurement, derive_run_id
from core.plugin import Source
from core.rules import RULE_REGISTRY
from db.connection import Conn
from db.repos import assessments as assessment_repo
from db.repos import datasets as dataset_repo
from db.repos import findings as finding_repo
from db.repos import measurements as measurement_repo
from db.repos import memberships
from db.repos import runs as run_repo
from plugins.tabular import TabularPlugin

# Numeric Arrow types that support descriptive / normality / correlation.
_NUMERIC_DTYPES: frozenset[str] = frozenset(
    {
        "int8",
        "int16",
        "int32",
        "int64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "float",
        "float16",
        "float32",
        "float64",
        "double",
        "decimal128",
        "decimal256",
    }
)

DEFAULT_GOALS: tuple[str, ...] = ("data_quality", "modeling_readiness")


def run_pipeline(
    conn: Conn,
    dataset_id: str,
    plugin_name: str = "tabular",
    goals: tuple[str, ...] = DEFAULT_GOALS,
) -> str:
    """Run the analysis pipeline for a stored dataset and persist results.

    Returns the run_id (idempotent: re-running with identical inputs is a no-op).
    """
    if plugin_name != "tabular":
        raise ValueError(
            f"Unsupported plugin {plugin_name!r}; only 'tabular' is available"
        )

    dataset_row = dataset_repo.get(conn, dataset_id)
    if dataset_row is None:
        raise ValueError(f"Dataset {dataset_id!r} not found")

    upload_dir = Path(str(dataset_row["upload_dir"]))
    manifest: list[dict[str, str]] = list(dataset_row["manifest"])
    paths = tuple(upload_dir / item["path"] for item in manifest)
    source = Source(paths=paths)

    plugin = TabularPlugin()
    ds = plugin.open(source)

    # ── cheap capabilities ────────────────────────────────────────────────────

    measurements: list[Measurement] = []

    cols = ds.columns()
    numeric_col_names = [c.name for c in cols if c.dtype_str in _NUMERIC_DTYPES]

    for col in cols:
        col_name = col.name
        for cap_id in (
            "tabular.column.missing",
            "tabular.column.frequency",
            "tabular.column.uniqueness",
        ):
            try:
                result = plugin.run(cap_id, ds, column=col_name)
                measurements.extend(result.measurements)
            except Exception:
                pass

    for col_name in numeric_col_names:
        for cap_id in ("tabular.column.descriptive", "tabular.column.normality"):
            try:
                result = plugin.run(cap_id, ds, column=col_name)
                measurements.extend(result.measurements)
            except Exception:
                pass

    try:
        result = plugin.run("tabular.dataset.row_dedup", ds)
        measurements.extend(result.measurements)
    except Exception:
        pass

    for i, col_a in enumerate(numeric_col_names):
        for col_b in numeric_col_names[i + 1 :]:
            try:
                result = plugin.run(
                    "tabular.pair.correlation", ds, column_a=col_a, column_b=col_b
                )
                measurements.extend(result.measurements)
            except Exception:
                pass

    # ── rules ─────────────────────────────────────────────────────────────────

    findings: list[Finding] = RULE_REGISTRY.run_findings(dataset_id, measurements)

    all_assessments: list[Assessment] = []
    for goal in goals:
        all_assessments.extend(
            RULE_REGISTRY.run_assessments(dataset_id, goal, findings)
        )

    # ── derive run_id ─────────────────────────────────────────────────────────

    producer_versions = {plugin.name: plugin.version}
    # No user-supplied config in this MVP; digest over goals for reproducibility.
    config_digest = hashlib.sha256(",".join(sorted(goals)).encode()).hexdigest()
    run_id = derive_run_id(dataset_id, producer_versions, config_digest)

    # ── persist ───────────────────────────────────────────────────────────────

    run_repo.upsert(conn, run_id, dataset_id, producer_versions, config_digest)

    for m in measurements:
        measurement_repo.upsert(conn, m)
        memberships.upsert_measurement(conn, run_id, m.id)

    for f in findings:
        finding_repo.upsert(conn, f)
        memberships.upsert_finding(conn, run_id, f.id)

    for a in all_assessments:
        assessment_repo.upsert(conn, a)
        memberships.upsert_assessment(conn, run_id, a.id)

    return run_id

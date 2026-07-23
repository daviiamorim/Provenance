"""TabularPlugin — DomainPlugin implementation for CSV and Parquet sources."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.parquet as pq

from core.model import (
    CapabilityResult,
    Measurement,
    Provenance,
    Scope,
    ScopeKind,
    derive_dataset_id,
)
from core.plugin import Capability, Catalog, Dataset, SniffResult, Source
from plugins.tabular._digest import canonical_dtype, column_digest, pair_digest
from plugins.tabular._stats import (
    compute_correlation,
    compute_descriptive,
    compute_frequency,
    compute_missing,
    compute_normality,
    compute_uniqueness,
)

__all__ = ["TabularDataset", "TabularPlugin"]

# ── constants ─────────────────────────────────────────────────────────────────

_CSV_EXTENSIONS: frozenset[str] = frozenset({".csv", ".tsv"})
_PARQUET_EXTENSIONS: frozenset[str] = frozenset({".parquet", ".pq"})
_PARQUET_MAGIC = b"PAR1"

DEFAULT_NULL_SENTINELS: Final[tuple[str, ...]] = (
    "", "N/A", "NA", "NULL", "NaN", "None", "n/a", "na", "nan", "null"
)

_NUMERIC_DTYPES: Final[frozenset[str]] = frozenset({
    "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
    "float", "float16", "float32", "float64", "double",
    "decimal128", "decimal256",
})

_NORMALITY_N_CUTOFF: Final = 5000

_CAPABILITY_TO_TYPE: dict[str, str] = {
    "tabular.column.missing": "core.quality.missing",
    "tabular.column.descriptive": "core.stats.descriptive",
    "tabular.column.frequency": "core.stats.frequency",
    "tabular.column.uniqueness": "core.quality.uniqueness",
    "tabular.column.normality": "core.stats.normality",
    "tabular.pair.correlation": "core.stats.correlation",
}

# ── helpers ───────────────────────────────────────────────────────────────────


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65_536), b""):
            h.update(block)
    return h.hexdigest()


def _is_parquet_path(path: Path) -> bool:
    return path.suffix.lower() in _PARQUET_EXTENSIONS


def _is_csv_path(path: Path) -> bool:
    return path.suffix.lower() in _CSV_EXTENSIONS


def _check_parquet_magic(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(4) == _PARQUET_MAGIC
    except OSError:
        return False


def _require_numeric(ds: TabularDataset, *col_names: str) -> None:
    """Raise TypeError if any of the named columns is not a numeric Arrow type."""
    for col_name in col_names:
        dtype = ds.column_dtype(col_name)
        if dtype not in _NUMERIC_DTYPES:
            raise TypeError(
                f"Column {col_name!r} has Arrow type {dtype!r}; "
                "this capability requires a numeric column. "
                "If the column contains numeric values mixed with sentinel strings "
                f"(e.g. 'N/A', ''), configure null_sentinels on TabularPlugin."
            )


@dataclass(frozen=True)
class _ColumnInfo:
    name: str
    dtype_str: str


# ── TabularDataset ────────────────────────────────────────────────────────────


class TabularDataset:
    """Lazy-loading tabular dataset backed by one or more CSV or Parquet files.

    Column data is not loaded until column_array() is called.
    """

    def __init__(
        self,
        source: Source,
        file_digests: list[tuple[str, str]],
        schema: pa.Schema,
        *,
        is_parquet: bool,
        null_sentinels: tuple[str, ...],
    ) -> None:
        self._source = source
        self._file_digests = file_digests
        self._schema = schema
        self._is_parquet = is_parquet
        self._null_sentinels = null_sentinels
        self._dataset_id = derive_dataset_id(file_digests)

    # ── Dataset protocol ──────────────────────────────────────────────────────

    @property
    def dataset_id(self) -> str:
        return self._dataset_id

    @property
    def source(self) -> Source:
        return self._source

    @property
    def null_sentinels(self) -> tuple[str, ...]:
        return self._null_sentinels

    def manifest(self) -> list[tuple[str, str]]:
        return list(self._file_digests)

    # ── column access ─────────────────────────────────────────────────────────

    def columns(self) -> list[_ColumnInfo]:
        return [
            _ColumnInfo(
                name=self._schema.field(name).name,
                dtype_str=canonical_dtype(self._schema.field(name).type),
            )
            for name in self._schema.names
        ]

    def column_dtype(self, col_name: str) -> str:
        idx = self._schema.get_field_index(col_name)
        if idx < 0:
            raise KeyError(f"Column {col_name!r} not found in dataset schema")
        return canonical_dtype(self._schema.field(idx).type)

    def column_array(self, col_name: str) -> pa.ChunkedArray:
        """Load a single column from all source files as a ChunkedArray."""
        if self._schema.get_field_index(col_name) < 0:
            raise KeyError(f"Column {col_name!r} not found in dataset schema")
        if self._is_parquet:
            return self._read_parquet_column(col_name)
        return self._read_csv_column(col_name)

    def _read_parquet_column(self, col_name: str) -> pa.ChunkedArray:
        chunks: list[pa.Array] = []
        for path in self._source.paths:
            table = pq.read_table(path, columns=[col_name])
            col = table.column(col_name)
            chunks.extend(col.chunks)
        return pa.chunked_array(chunks, type=self._schema.field(col_name).type)

    def _read_csv_column(self, col_name: str) -> pa.ChunkedArray:
        convert_opts = pa_csv.ConvertOptions(
            null_values=list(self._null_sentinels),
            strings_can_be_null=True,
        )
        chunks: list[pa.Array] = []
        for path in self._source.paths:
            reader = pa_csv.open_csv(path, convert_options=convert_opts)
            for batch in reader:
                idx = batch.schema.get_field_index(col_name)
                if idx >= 0:
                    chunks.append(batch.column(idx))
        return pa.chunked_array(chunks)


# ── TabularPlugin ─────────────────────────────────────────────────────────────


class TabularPlugin:
    """Domain plugin for tabular data (CSV and Parquet).

    Implements six cheap capabilities emitting the six core measurement types.
    """

    name: str = "tabular"
    version: str = "0.1.0"

    def __init__(
        self,
        null_sentinels: tuple[str, ...] = DEFAULT_NULL_SENTINELS,
    ) -> None:
        self._null_sentinels = null_sentinels

    def sniff(self, source: Source) -> SniffResult:  # noqa: PLR0911
        if not source.paths:
            return SniffResult(confidence=0.0, evidence="No paths provided")

        # Honour explicit media_type
        if source.media_type in ("text/csv", "text/tab-separated-values"):
            return SniffResult(
                confidence=0.95,
                evidence=f"Explicit media_type {source.media_type!r}",
            )
        if source.media_type == "application/vnd.apache.parquet":
            return SniffResult(
                confidence=0.95,
                evidence="Explicit media_type 'application/vnd.apache.parquet'",
            )

        extensions = {p.suffix.lower() for p in source.paths}

        if extensions <= _CSV_EXTENSIONS:
            return SniffResult(
                confidence=0.85,
                evidence=f"All paths have CSV/TSV extension: {sorted(extensions)}",
            )

        if extensions <= _PARQUET_EXTENSIONS:
            if _check_parquet_magic(source.paths[0]):
                return SniffResult(
                    confidence=0.99,
                    evidence="Parquet magic bytes PAR1 confirmed",
                )
            return SniffResult(
                confidence=0.85,
                evidence=f"All paths have Parquet extension: {sorted(extensions)}",
            )

        return SniffResult(
            confidence=0.0,
            evidence=f"Unrecognised or mixed extensions: {sorted(extensions)}",
        )

    def open(self, source: Source) -> TabularDataset:
        """Open a CSV or Parquet source lazily (no full data load)."""
        if not source.paths:
            raise ValueError("Source must have at least one path")

        extensions = {p.suffix.lower() for p in source.paths}
        is_parquet = bool(extensions <= _PARQUET_EXTENSIONS)
        is_csv = bool(extensions <= _CSV_EXTENSIONS)

        if source.media_type == "application/vnd.apache.parquet":
            is_parquet, is_csv = True, False
        elif source.media_type in ("text/csv", "text/tab-separated-values"):
            is_parquet, is_csv = False, True

        if not is_parquet and not is_csv:
            raise ValueError(
                f"TabularPlugin cannot open files with extensions {sorted(extensions)}"
            )

        # Stream-hash files — O(1) memory, no full load
        file_digests = [
            (str(p.name), _file_sha256(p)) for p in source.paths
        ]

        schema = self._read_schema(
            source.paths, is_parquet=is_parquet, null_sentinels=self._null_sentinels
        )
        return TabularDataset(
            source,
            file_digests,
            schema,
            is_parquet=is_parquet,
            null_sentinels=self._null_sentinels,
        )

    def catalog(self) -> Catalog:
        _col_schema: dict[str, object] = {
            "type": "object",
            "properties": {"column": {"type": "string"}},
            "required": ["column"],
            "additionalProperties": False,
        }
        _pair_schema: dict[str, object] = {
            "type": "object",
            "properties": {
                "column_a": {"type": "string"},
                "column_b": {"type": "string"},
                "method": {
                    "type": "string",
                    "enum": ["pearson", "spearman", "kendall"],
                    "default": "pearson",
                },
            },
            "required": ["column_a", "column_b"],
            "additionalProperties": False,
        }
        return Catalog(
            capabilities=(
                Capability(
                    id="tabular.column.missing",
                    description="Missing value count and proportion for a column.",
                    params_schema=_col_schema,
                    produces=("core.quality.missing",),
                    renders=False,
                    cost="cheap",
                ),
                Capability(
                    id="tabular.column.descriptive",
                    description=(
                        "Descriptive statistics (mean, std, quartiles)"
                        " for a numeric column."
                    ),
                    params_schema=_col_schema,
                    produces=("core.stats.descriptive",),
                    renders=False,
                    cost="cheap",
                ),
                Capability(
                    id="tabular.column.frequency",
                    description="Frequency distribution for a column.",
                    params_schema=_col_schema,
                    produces=("core.stats.frequency",),
                    renders=False,
                    cost="cheap",
                ),
                Capability(
                    id="tabular.column.uniqueness",
                    description=(
                        "Uniqueness metrics (distinct count, duplicate rate)"
                        " for a column."
                    ),
                    params_schema=_col_schema,
                    produces=("core.quality.uniqueness",),
                    renders=False,
                    cost="cheap",
                ),
                Capability(
                    id="tabular.column.normality",
                    description=(
                        "Normality test (Shapiro-Wilk ≤5000 rows, "
                        "D'Agostino-Pearson >5000) for a numeric column."
                    ),
                    params_schema=_col_schema,
                    produces=("core.stats.normality",),
                    renders=False,
                    cost="cheap",
                ),
                Capability(
                    id="tabular.pair.correlation",
                    description=(
                        "Pairwise correlation coefficient between two numeric columns."
                    ),
                    params_schema=_pair_schema,
                    produces=("core.stats.correlation",),
                    renders=False,
                    cost="cheap",
                ),
            ),
            measurement_types=(
                "core.quality.missing",
                "core.stats.descriptive",
                "core.stats.frequency",
                "core.quality.uniqueness",
                "core.stats.normality",
                "core.stats.correlation",
            ),
        )

    def run(
        self, capability_id: str, ds: Dataset, **params: object
    ) -> CapabilityResult:
        if not isinstance(ds, TabularDataset):
            raise TypeError(
                "TabularPlugin.run() requires a TabularDataset, "
                f"got {type(ds).__name__}"
            )
        if capability_id not in _CAPABILITY_TO_TYPE:
            raise ValueError(
                f"Unknown capability {capability_id!r}. "
                f"Available: {sorted(_CAPABILITY_TO_TYPE)}"
            )

        t0 = time.perf_counter()
        payload, scope, prov_params, input_dig = self._dispatch(
            capability_id, ds, params
        )
        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))

        provenance = Provenance(
            producer="plugins.tabular",
            version=self.version,
            params=prov_params,
            input_digest=input_dig,
            duration_ms=duration_ms,
            seed=None,
        )
        msr = Measurement.create(
            dataset_id=ds.dataset_id,
            type=_CAPABILITY_TO_TYPE[capability_id],
            scope=scope,
            payload=payload,
            provenance=provenance,
        )
        return CapabilityResult(measurements=(msr,), artifacts=())

    # ── private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _read_schema(
        paths: tuple[Path, ...],
        *,
        is_parquet: bool,
        null_sentinels: tuple[str, ...],
    ) -> pa.Schema:
        if is_parquet:
            return pq.read_schema(paths[0])
        convert_opts = pa_csv.ConvertOptions(
            null_values=list(null_sentinels),
            strings_can_be_null=True,
        )
        reader = pa_csv.open_csv(paths[0], convert_options=convert_opts)
        return reader.schema

    @staticmethod
    def _col_digest(ds: TabularDataset, col_name: str) -> tuple[pa.ChunkedArray, str]:
        col = ds.column_array(col_name)
        dig = column_digest(ds.column_dtype(col_name), iter(col.to_pylist()))
        return col, dig

    def _dispatch(
        self,
        capability_id: str,
        ds: TabularDataset,
        params: dict[str, object],
    ) -> tuple[dict[str, object], Scope, dict[str, object], str]:
        _sentinels_param: dict[str, object] = {
            "null_sentinels": sorted(ds.null_sentinels)
        }

        if capability_id == "tabular.column.missing":
            col_name = str(params["column"])
            col, dig = self._col_digest(ds, col_name)
            return (
                compute_missing(col),
                Scope(kind=ScopeKind.COLUMN, refs=(col_name,)),
                _sentinels_param,
                dig,
            )

        if capability_id == "tabular.column.descriptive":
            col_name = str(params["column"])
            _require_numeric(ds, col_name)
            col, dig = self._col_digest(ds, col_name)
            return (
                compute_descriptive(col),
                Scope(kind=ScopeKind.COLUMN, refs=(col_name,)),
                {**_sentinels_param, "quartile_method": "linear", "ddof": 1},
                dig,
            )

        if capability_id == "tabular.column.frequency":
            col_name = str(params["column"])
            col, dig = self._col_digest(ds, col_name)
            return (
                compute_frequency(col),
                Scope(kind=ScopeKind.COLUMN, refs=(col_name,)),
                _sentinels_param,
                dig,
            )

        if capability_id == "tabular.column.uniqueness":
            col_name = str(params["column"])
            col, dig = self._col_digest(ds, col_name)
            return (
                compute_uniqueness(col),
                Scope(kind=ScopeKind.COLUMN, refs=(col_name,)),
                _sentinels_param,
                dig,
            )

        if capability_id == "tabular.column.normality":
            col_name = str(params["column"])
            _require_numeric(ds, col_name)
            col, dig = self._col_digest(ds, col_name)
            return (
                compute_normality(col, n_cutoff=_NORMALITY_N_CUTOFF),
                Scope(kind=ScopeKind.COLUMN, refs=(col_name,)),
                {**_sentinels_param, "n_cutoff": _NORMALITY_N_CUTOFF},
                dig,
            )

        # tabular.pair.correlation
        col_a = str(params["column_a"])
        col_b = str(params["column_b"])
        method = str(params.get("method", "pearson"))
        _require_numeric(ds, col_a, col_b)
        arr_a, dig_a = self._col_digest(ds, col_a)
        arr_b, dig_b = self._col_digest(ds, col_b)
        return (
            compute_correlation(arr_a, arr_b, method=method),
            Scope(kind=ScopeKind.PAIR, refs=(col_a, col_b)),
            {**_sentinels_param, "method": method, "missing": "pairwise"},
            pair_digest(dig_a, dig_b),
        )

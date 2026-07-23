"""Test suite for plugins/tabular — Etapa 2.

Covers: digest anchor, pair symmetry, all six capabilities (CSV + Parquet),
sniff confidence, open() lazy loading, Dataset protocol, missing/uniqueness
edge cases, normality regime selection, and correlation symmetry.
"""

from __future__ import annotations

import csv
import datetime
import io
import math
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from core.model import CapabilityResult, ScopeKind
from core.plugin import SniffResult, Source
from plugins.tabular import TabularDataset, TabularPlugin
from plugins.tabular._digest import canonical_dtype, column_digest, pair_digest
from plugins.tabular._stats import (
    compute_correlation,
    compute_descriptive,
    compute_frequency,
    compute_missing,
    compute_normality,
    compute_uniqueness,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _csv_file(tmp_path: Path, name: str, rows: list[dict[str, object]]) -> Path:
    """Write a CSV file to tmp_path and return its Path."""
    path = tmp_path / name
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    fieldnames = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")
    return path


def _parquet_file(tmp_path: Path, name: str, table: pa.Table) -> Path:
    path = tmp_path / name
    pq.write_table(table, path)
    return path


def _simple_csv(tmp_path: Path) -> Path:
    """CSV with numeric column 'val' and string column 'cat'."""
    return _csv_file(
        tmp_path,
        "data.csv",
        [
            {"val": 1, "cat": "a"},
            {"val": 2, "cat": "b"},
            {"val": 3, "cat": "a"},
            {"val": 4, "cat": "c"},
            {"val": 5, "cat": "b"},
        ],
    )


def _simple_parquet(tmp_path: Path) -> Path:
    table = pa.table(
        {
            "val": pa.array([1, 2, 3, 4, 5], type=pa.int64()),
            "cat": pa.array(["a", "b", "a", "c", "b"], type=pa.string()),
        }
    )
    return _parquet_file(tmp_path, "data.parquet", table)


# ── TestDigestAnchor ──────────────────────────────────────────────────────────


class TestDigestAnchor:
    """Anchor tests freeze the expected digest hex so any format drift is caught."""

    # These values were computed on 2026-07-22 and must not change.
    ANCHOR_INT64_1_2_NULL = (
        "d65b1e1c914115b24a3f4d5ac770e19a6224cf58b3c489a3844fc1edd63af762"
    )
    ANCHOR_STRING_A_NULL_B = (
        "13e8b8d1d22bfa5f73b55f0600efa9e00a70baf916878c1a032a575f207daf17"
    )

    def test_int64_anchor(self) -> None:
        assert column_digest("int64", iter([1, 2, None])) == self.ANCHOR_INT64_1_2_NULL

    def test_string_anchor(self) -> None:
        result = column_digest("string", iter(["a", None, "b"]))
        assert result == self.ANCHOR_STRING_A_NULL_B

    def test_pair_digest_symmetric(self) -> None:
        dig_a = column_digest("int64", iter([1, 2, 3]))
        dig_b = column_digest("float64", iter([1.5, 2.5, 3.5]))
        assert pair_digest(dig_a, dig_b) == pair_digest(dig_b, dig_a)

    def test_pair_digest_anchor(self) -> None:
        dig_a = column_digest("int64", iter([1, 2, 3]))
        dig_b = column_digest("float64", iter([1.5, 2.5, 3.5]))
        expected = "3ea5d894f62c653aff1b1a69210a82edf04ad6422050e02558aa4656be2db2be"
        assert pair_digest(dig_a, dig_b) == expected

    def test_null_distinct_from_value_null_string(self) -> None:
        # None (Arrow null) must produce a different digest than the string "null"
        dig_none = column_digest("string", iter([None]))
        dig_str = column_digest("string", iter(["null"]))
        assert dig_none != dig_str

    def test_nan_distinct_from_none(self) -> None:
        dig_nan = column_digest("float64", iter([float("nan")]))
        dig_none = column_digest("float64", iter([None]))
        assert dig_nan != dig_none

    def test_dtype_changes_digest(self) -> None:
        dig_int = column_digest("int64", iter([1]))
        dig_float = column_digest("float64", iter([1]))
        assert dig_int != dig_float

    def test_order_matters(self) -> None:
        dig_12 = column_digest("int64", iter([1, 2]))
        dig_21 = column_digest("int64", iter([2, 1]))
        assert dig_12 != dig_21

    def test_empty_column(self) -> None:
        dig = column_digest("int64", iter([]))
        assert len(dig) == 64  # 32 bytes hex


class TestCanonicalDtype:
    def test_primitive_types(self) -> None:
        assert canonical_dtype(pa.int64()) == "int64"
        assert canonical_dtype(pa.float64()) == "double"
        assert canonical_dtype(pa.string()) == "string"
        assert canonical_dtype(pa.bool_()) == "bool"
        assert canonical_dtype(pa.null()) == "null"

    def test_parameterised_types(self) -> None:
        # These stable strings come from pyarrow's Arrow-spec representation
        ts = canonical_dtype(pa.timestamp("us", tz="UTC"))
        assert "timestamp" in ts
        assert "us" in ts


# ── TestSniff ─────────────────────────────────────────────────────────────────


class TestSniff:
    def setup_method(self) -> None:
        self.plugin = TabularPlugin()

    def test_no_paths(self) -> None:
        r = self.plugin.sniff(Source(paths=()))
        assert r.confidence == 0.0

    def test_csv_extension(self, tmp_path: Path) -> None:
        p = tmp_path / "data.csv"
        p.write_text("a,b\n1,2\n", encoding="utf-8")
        r = self.plugin.sniff(Source(paths=(p,)))
        assert r.confidence >= 0.8

    def test_parquet_magic_bytes(self, tmp_path: Path) -> None:
        p = _simple_parquet(tmp_path)
        r = self.plugin.sniff(Source(paths=(p,)))
        assert r.confidence >= 0.99

    def test_explicit_media_type_csv(self, tmp_path: Path) -> None:
        p = tmp_path / "data.csv"
        p.write_text("a\n1\n", encoding="utf-8")
        r = self.plugin.sniff(Source(paths=(p,), media_type="text/csv"))
        assert r.confidence >= 0.95

    def test_explicit_media_type_parquet(self, tmp_path: Path) -> None:
        p = _simple_parquet(tmp_path)
        r = self.plugin.sniff(
            Source(paths=(p,), media_type="application/vnd.apache.parquet")
        )
        assert r.confidence >= 0.95

    def test_mixed_extensions_returns_zero(self, tmp_path: Path) -> None:
        csv_p = tmp_path / "a.csv"
        csv_p.write_text("x\n1\n", encoding="utf-8")
        pq_p = _simple_parquet(tmp_path)
        r = self.plugin.sniff(Source(paths=(csv_p, pq_p)))
        assert r.confidence == 0.0

    def test_unknown_extension_returns_zero(self, tmp_path: Path) -> None:
        p = tmp_path / "data.json"
        p.write_text("{}", encoding="utf-8")
        r = self.plugin.sniff(Source(paths=(p,)))
        assert r.confidence == 0.0

    def test_sniff_result_has_evidence(self, tmp_path: Path) -> None:
        p = _simple_parquet(tmp_path)
        r = self.plugin.sniff(Source(paths=(p,)))
        assert isinstance(r, SniffResult)
        assert r.evidence


# ── TestOpen ──────────────────────────────────────────────────────────────────


class TestOpen:
    def setup_method(self) -> None:
        self.plugin = TabularPlugin()

    def test_open_csv_returns_dataset(self, tmp_path: Path) -> None:
        p = _simple_csv(tmp_path)
        ds = self.plugin.open(Source(paths=(p,)))
        assert isinstance(ds, TabularDataset)

    def test_open_parquet_returns_dataset(self, tmp_path: Path) -> None:
        p = _simple_parquet(tmp_path)
        ds = self.plugin.open(Source(paths=(p,)))
        assert isinstance(ds, TabularDataset)

    def test_dataset_id_is_stable_csv(self, tmp_path: Path) -> None:
        p = _simple_csv(tmp_path)
        src = Source(paths=(p,))
        ds1 = self.plugin.open(src)
        ds2 = self.plugin.open(src)
        assert ds1.dataset_id == ds2.dataset_id

    def test_dataset_id_is_stable_parquet(self, tmp_path: Path) -> None:
        p = _simple_parquet(tmp_path)
        src = Source(paths=(p,))
        ds1 = self.plugin.open(src)
        ds2 = self.plugin.open(src)
        assert ds1.dataset_id == ds2.dataset_id

    def test_dataset_id_changes_when_content_changes(self, tmp_path: Path) -> None:
        p1 = _csv_file(tmp_path, "a.csv", [{"x": 1}])
        p2 = _csv_file(tmp_path, "b.csv", [{"x": 2}])
        ds1 = self.plugin.open(Source(paths=(p1,)))
        ds2 = self.plugin.open(Source(paths=(p2,)))
        assert ds1.dataset_id != ds2.dataset_id

    def test_dataset_id_has_dset_prefix(self, tmp_path: Path) -> None:
        p = _simple_csv(tmp_path)
        ds = self.plugin.open(Source(paths=(p,)))
        assert ds.dataset_id.startswith("dset-")

    def test_manifest_returns_file_digests(self, tmp_path: Path) -> None:
        p = _simple_csv(tmp_path)
        ds = self.plugin.open(Source(paths=(p,)))
        manifest = ds.manifest()
        assert len(manifest) == 1
        name, digest = manifest[0]
        assert name == "data.csv"
        assert len(digest) == 64  # sha256 hex

    def test_open_empty_source_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one path"):
            self.plugin.open(Source(paths=()))

    def test_source_property(self, tmp_path: Path) -> None:
        p = _simple_csv(tmp_path)
        src = Source(paths=(p,))
        ds = self.plugin.open(src)
        assert ds.source is src

    def test_unknown_extension_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "data.json"
        p.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="TabularPlugin cannot open"):
            self.plugin.open(Source(paths=(p,)))


# ── TestCatalog ───────────────────────────────────────────────────────────────


class TestCatalog:
    def setup_method(self) -> None:
        self.plugin = TabularPlugin()
        self.catalog = self.plugin.catalog()

    def test_six_capabilities(self) -> None:
        assert len(self.catalog.capabilities) == 6

    def test_capability_ids(self) -> None:
        ids = {c.id for c in self.catalog.capabilities}
        assert "tabular.column.missing" in ids
        assert "tabular.column.descriptive" in ids
        assert "tabular.column.frequency" in ids
        assert "tabular.column.uniqueness" in ids
        assert "tabular.column.normality" in ids
        assert "tabular.pair.correlation" in ids

    def test_all_capabilities_cheap(self) -> None:
        for cap in self.catalog.capabilities:
            assert cap.cost == "cheap"

    def test_measurement_types(self) -> None:
        types = set(self.catalog.measurement_types)
        assert "core.quality.missing" in types
        assert "core.stats.descriptive" in types
        assert "core.stats.frequency" in types
        assert "core.quality.uniqueness" in types
        assert "core.stats.normality" in types
        assert "core.stats.correlation" in types


# ── TestMissing ───────────────────────────────────────────────────────────────


class TestMissing:
    def test_no_nulls(self) -> None:
        col = pa.array([1, 2, 3], type=pa.int64())
        result = compute_missing(col)
        assert result["total_count"] == 3
        assert result["missing_count"] == 0
        assert result["missing_proportion"] == 0.0

    def test_all_nulls(self) -> None:
        col = pa.array([None, None], type=pa.int64())
        result = compute_missing(col)
        assert result["missing_count"] == 2
        assert result["missing_proportion"] == 1.0

    def test_partial_nulls(self) -> None:
        col = pa.array([1, None, 3, None], type=pa.int64())
        result = compute_missing(col)
        assert result["total_count"] == 4
        assert result["missing_count"] == 2
        assert math.isclose(result["missing_proportion"], 0.5)  # type: ignore[arg-type]

    def test_empty_column(self) -> None:
        col = pa.array([], type=pa.int64())
        result = compute_missing(col)
        assert result["total_count"] == 0
        assert result["missing_proportion"] == 0.0


# ── TestDescriptive ───────────────────────────────────────────────────────────


class TestDescriptive:
    def test_basic(self) -> None:
        col = pa.array([1.0, 2.0, 3.0, 4.0, 5.0], type=pa.float64())
        r = compute_descriptive(col)
        assert r["count"] == 5
        assert math.isclose(r["mean"], 3.0)  # type: ignore[arg-type]
        assert r["min"] == 1.0
        assert r["max"] == 5.0
        assert r["null_count"] == 0

    def test_nulls_excluded(self) -> None:
        col = pa.array([1.0, None, 3.0], type=pa.float64())
        r = compute_descriptive(col)
        assert r["count"] == 2
        assert r["null_count"] == 1

    def test_single_value_std_is_zero(self) -> None:
        col = pa.array([42.0], type=pa.float64())
        r = compute_descriptive(col)
        assert r["std"] == 0.0

    def test_quartiles_known_values(self) -> None:
        # [1,2,3,4] → q25=1.75, q50=2.5, q75=3.25 with linear method
        col = pa.array([1.0, 2.0, 3.0, 4.0], type=pa.float64())
        r = compute_descriptive(col)
        assert math.isclose(r["q25"], 1.75)  # type: ignore[arg-type]
        assert math.isclose(r["q50"], 2.5)  # type: ignore[arg-type]
        assert math.isclose(r["q75"], 3.25)  # type: ignore[arg-type]

    def test_std_is_sample(self) -> None:
        col = pa.array([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0], type=pa.float64())
        r = compute_descriptive(col)
        expected = float(np.std([2, 4, 4, 4, 5, 5, 7, 9], ddof=1))
        assert math.isclose(r["std"], expected)  # type: ignore[arg-type]

    def test_fully_null_raises(self) -> None:
        col = pa.array([None, None], type=pa.float64())
        with pytest.raises(ValueError, match="fully-null"):
            compute_descriptive(col)


# ── TestFrequency ─────────────────────────────────────────────────────────────


class TestFrequency:
    def test_basic(self) -> None:
        col = pa.array(["a", "b", "a", "c"], type=pa.string())
        r = compute_frequency(col)
        assert r["total_count"] == 4
        freqs = r["frequencies"]
        assert isinstance(freqs, list)
        # "a" appears 2 times, should be first
        assert freqs[0]["value"] == "a"
        assert freqs[0]["count"] == 2

    def test_proportions_sum_to_one(self) -> None:
        col = pa.array(["x", "y", "x", "z", "y", "x"], type=pa.string())
        r = compute_frequency(col)
        total = sum(item["proportion"] for item in r["frequencies"])
        assert math.isclose(total, 1.0)

    def test_null_count_present_when_nulls(self) -> None:
        col = pa.array(["a", None, "b", None], type=pa.string())
        r = compute_frequency(col)
        assert r.get("null_count") == 2

    def test_null_count_absent_when_no_nulls(self) -> None:
        col = pa.array(["a", "b"], type=pa.string())
        r = compute_frequency(col)
        assert "null_count" not in r

    def test_nulls_excluded_from_proportions(self) -> None:
        col = pa.array(["a", "a", None], type=pa.string())
        r = compute_frequency(col)
        assert len(r["frequencies"]) == 1
        assert r["frequencies"][0]["proportion"] == 1.0


# ── TestUniqueness ────────────────────────────────────────────────────────────


class TestUniqueness:
    def test_all_unique(self) -> None:
        col = pa.array([1, 2, 3, 4], type=pa.int64())
        r = compute_uniqueness(col)
        assert r["total_count"] == 4
        assert r["unique_count"] == 4
        assert r["duplicate_count"] == 0
        assert r["unique_proportion"] == 1.0

    def test_all_same(self) -> None:
        col = pa.array([7, 7, 7], type=pa.int64())
        r = compute_uniqueness(col)
        assert r["unique_count"] == 1
        assert r["duplicate_count"] == 2

    def test_total_count_includes_nulls(self) -> None:
        col = pa.array([1, None, 2, None], type=pa.int64())
        r = compute_uniqueness(col)
        # total_count is all rows including nulls — consistent with core.quality.missing
        assert r["total_count"] == 4
        assert r["null_count"] == 2
        assert r["unique_count"] == 2

    def test_null_count_absent_when_no_nulls(self) -> None:
        col = pa.array([1, 2, 3], type=pa.int64())
        r = compute_uniqueness(col)
        assert "null_count" not in r

    def test_proportion_correct(self) -> None:
        col = pa.array([1, 1, 2, 3], type=pa.int64())
        r = compute_uniqueness(col)
        # 3 unique out of 4 non-null
        assert math.isclose(r["unique_proportion"], 3 / 4)


# ── TestNormality ─────────────────────────────────────────────────────────────


class TestNormality:
    def test_shapiro_for_small_sample(self) -> None:
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, 100).tolist()
        col = pa.array(data, type=pa.float64())
        r = compute_normality(col)
        assert r["test"] == "shapiro_wilk"
        assert r["sample_size"] == 100
        assert 0.0 <= r["p_value"] <= 1.0  # type: ignore[operator]

    def test_dagostino_for_large_sample(self) -> None:
        rng = np.random.default_rng(0)
        data = rng.normal(0, 1, 6000).tolist()
        col = pa.array(data, type=pa.float64())
        r = compute_normality(col)
        assert r["test"] == "dagostino_pearson"
        assert r["sample_size"] == 6000

    def test_nulls_excluded(self) -> None:
        rng = np.random.default_rng(7)
        data: list[object] = [None, None, *rng.normal(0, 1, 50).tolist()]
        col = pa.array(data, type=pa.float64())
        r = compute_normality(col)
        assert r["sample_size"] == 50

    def test_too_few_values_raises(self) -> None:
        col = pa.array([1.0, 2.0], type=pa.float64())
        with pytest.raises(ValueError, match="at least 3"):
            compute_normality(col)

    def test_statistic_is_float(self) -> None:
        data = np.random.default_rng(1).normal(0, 1, 20).tolist()
        col = pa.array(data, type=pa.float64())
        r = compute_normality(col)
        assert isinstance(r["statistic"], float)
        assert isinstance(r["p_value"], float)


# ── TestCorrelation ───────────────────────────────────────────────────────────


class TestCorrelation:
    def test_perfect_positive(self) -> None:
        a = pa.array([1.0, 2.0, 3.0, 4.0, 5.0], type=pa.float64())
        r = compute_correlation(a, a)
        assert math.isclose(r["coefficient"], 1.0, abs_tol=1e-9)

    def test_perfect_negative(self) -> None:
        a = pa.array([1.0, 2.0, 3.0], type=pa.float64())
        b = pa.array([3.0, 2.0, 1.0], type=pa.float64())
        r = compute_correlation(a, b)
        assert math.isclose(r["coefficient"], -1.0, abs_tol=1e-9)

    def test_pairwise_deletion(self) -> None:
        # Row 2 has null in b — should be excluded
        a = pa.array([1.0, 2.0, 3.0], type=pa.float64())
        b = pa.array([2.0, None, 6.0], type=pa.float64())
        r = compute_correlation(a, b)
        assert r["sample_size"] == 2

    def test_spearman_method(self) -> None:
        a = pa.array([1.0, 2.0, 3.0, 4.0], type=pa.float64())
        b = pa.array([1.0, 2.0, 3.0, 4.0], type=pa.float64())
        r = compute_correlation(a, b, method="spearman")
        assert r["method"] == "spearman"
        assert math.isclose(r["coefficient"], 1.0, abs_tol=1e-9)

    def test_kendall_method(self) -> None:
        a = pa.array([1.0, 2.0, 3.0, 4.0], type=pa.float64())
        b = pa.array([1.0, 2.0, 3.0, 4.0], type=pa.float64())
        r = compute_correlation(a, b, method="kendall")
        assert r["method"] == "kendall"

    def test_unknown_method_raises(self) -> None:
        a = pa.array([1.0, 2.0, 3.0], type=pa.float64())
        with pytest.raises(ValueError, match="Unknown correlation method"):
            compute_correlation(a, a, method="cosine")

    def test_length_mismatch_raises(self) -> None:
        a = pa.array([1.0, 2.0], type=pa.float64())
        b = pa.array([1.0], type=pa.float64())
        with pytest.raises(ValueError, match="same length"):
            compute_correlation(a, b)

    def test_p_value_present(self) -> None:
        a = pa.array([1.0, 2.0, 3.0, 4.0], type=pa.float64())
        r = compute_correlation(a, a)
        assert "p_value" in r

    def test_coefficient_in_range(self) -> None:
        rng = np.random.default_rng(42)
        a = pa.array(rng.normal(0, 1, 50).tolist(), type=pa.float64())
        b = pa.array(rng.normal(0, 1, 50).tolist(), type=pa.float64())
        r = compute_correlation(a, b)
        assert -1.0 <= r["coefficient"] <= 1.0  # type: ignore[operator]


# ── TestRunCapability ─────────────────────────────────────────────────────────


class TestRunCapability:
    """Integration tests: plugin.run() → valid CapabilityResult + Measurement."""

    def setup_method(self) -> None:
        self.plugin = TabularPlugin()

    def _open_csv(self, tmp_path: Path) -> TabularDataset:
        p = _simple_csv(tmp_path)
        return self.plugin.open(Source(paths=(p,)))

    def _open_parquet(self, tmp_path: Path) -> TabularDataset:
        p = _simple_parquet(tmp_path)
        return self.plugin.open(Source(paths=(p,)))

    def test_missing_csv(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        result = self.plugin.run("tabular.column.missing", ds, column="val")
        self._assert_valid_result(result, "core.quality.missing", ScopeKind.COLUMN)

    def test_descriptive_csv(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        result = self.plugin.run("tabular.column.descriptive", ds, column="val")
        self._assert_valid_result(result, "core.stats.descriptive", ScopeKind.COLUMN)
        payload = dict(result.measurements[0].payload)
        assert payload["count"] == 5
        assert math.isclose(payload["mean"], 3.0)  # type: ignore[arg-type]

    def test_frequency_csv(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        result = self.plugin.run("tabular.column.frequency", ds, column="cat")
        self._assert_valid_result(result, "core.stats.frequency", ScopeKind.COLUMN)

    def test_uniqueness_csv(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        result = self.plugin.run("tabular.column.uniqueness", ds, column="cat")
        self._assert_valid_result(result, "core.quality.uniqueness", ScopeKind.COLUMN)

    def test_normality_csv(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        result = self.plugin.run("tabular.column.normality", ds, column="val")
        self._assert_valid_result(result, "core.stats.normality", ScopeKind.COLUMN)

    def test_correlation_csv(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        result = self.plugin.run(
            "tabular.pair.correlation", ds, column_a="val", column_b="val"
        )
        self._assert_valid_result(result, "core.stats.correlation", ScopeKind.PAIR)

    def test_all_six_parquet(self, tmp_path: Path) -> None:
        ds = self._open_parquet(tmp_path)
        ops = [
            ("tabular.column.missing", {"column": "val"}),
            ("tabular.column.descriptive", {"column": "val"}),
            ("tabular.column.frequency", {"column": "cat"}),
            ("tabular.column.uniqueness", {"column": "cat"}),
            ("tabular.column.normality", {"column": "val"}),
            ("tabular.pair.correlation", {"column_a": "val", "column_b": "val"}),
        ]
        for cap_id, params in ops:
            result = self.plugin.run(cap_id, ds, **params)
            assert isinstance(result, CapabilityResult)
            assert len(result.measurements) == 1

    def test_measurement_id_has_msr_prefix(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        result = self.plugin.run("tabular.column.missing", ds, column="val")
        assert result.measurements[0].id.startswith("msr-")

    def test_measurement_is_deterministic(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        r1 = self.plugin.run("tabular.column.missing", ds, column="val")
        r2 = self.plugin.run("tabular.column.missing", ds, column="val")
        assert r1.measurements[0].id == r2.measurements[0].id

    def test_different_columns_different_ids(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        r1 = self.plugin.run("tabular.column.missing", ds, column="val")
        r2 = self.plugin.run("tabular.column.missing", ds, column="cat")
        assert r1.measurements[0].id != r2.measurements[0].id

    def test_correlation_symmetric_id(self, tmp_path: Path) -> None:
        """corr(a, b) and corr(b, a) share the same measurement id."""
        p = _parquet_file(
            tmp_path,
            "xy.parquet",
            pa.table({
                "x": pa.array([1.0, 2.0, 3.0], type=pa.float64()),
                "y": pa.array([2.0, 4.0, 6.0], type=pa.float64()),
            }),
        )
        ds = self.plugin.open(Source(paths=(p,)))
        r_ab = self.plugin.run(
            "tabular.pair.correlation", ds, column_a="x", column_b="y"
        )
        r_ba = self.plugin.run(
            "tabular.pair.correlation", ds, column_a="y", column_b="x"
        )
        assert r_ab.measurements[0].id == r_ba.measurements[0].id

    def test_provenance_producer(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        result = self.plugin.run("tabular.column.missing", ds, column="val")
        prov = result.measurements[0].provenance
        assert prov.producer == "plugins.tabular"

    def test_unknown_capability_raises(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        with pytest.raises(ValueError, match="Unknown capability"):
            self.plugin.run("tabular.does.not.exist", ds)

    def test_wrong_dataset_type_raises(self) -> None:
        class _FakeDataset:
            dataset_id = "dset-abc"
            source = Source(paths=())

            def manifest(self) -> list[tuple[str, str]]:
                return []

        with pytest.raises(TypeError, match="TabularDataset"):
            self.plugin.run("tabular.column.missing", _FakeDataset(), column="x")  # type: ignore[arg-type]

    def test_missing_column_param_raises(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        with pytest.raises(KeyError):
            self.plugin.run("tabular.column.missing", ds)

    def test_scope_kind_column(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        result = self.plugin.run("tabular.column.missing", ds, column="val")
        assert result.measurements[0].scope.kind == ScopeKind.COLUMN

    def test_scope_kind_pair(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        result = self.plugin.run(
            "tabular.pair.correlation", ds, column_a="val", column_b="val"
        )
        assert result.measurements[0].scope.kind == ScopeKind.PAIR

    def test_normality_params_include_n_cutoff(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        result = self.plugin.run("tabular.column.normality", ds, column="val")
        prov = result.measurements[0].provenance
        assert prov.params.get("n_cutoff") == 5000

    def test_normality_params_include_null_sentinels(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        result = self.plugin.run("tabular.column.normality", ds, column="val")
        prov = result.measurements[0].provenance
        assert "null_sentinels" in prov.params

    def test_missing_params_include_null_sentinels(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        result = self.plugin.run("tabular.column.missing", ds, column="val")
        prov = result.measurements[0].provenance
        assert "null_sentinels" in prov.params

    def test_uniqueness_params_include_null_sentinels(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        result = self.plugin.run("tabular.column.uniqueness", ds, column="val")
        prov = result.measurements[0].provenance
        assert "null_sentinels" in prov.params

    def test_descriptive_rejects_string_column(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        with pytest.raises(TypeError, match="numeric column"):
            self.plugin.run("tabular.column.descriptive", ds, column="cat")

    def test_normality_rejects_string_column(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        with pytest.raises(TypeError, match="numeric column"):
            self.plugin.run("tabular.column.normality", ds, column="cat")

    def test_correlation_rejects_string_column(self, tmp_path: Path) -> None:
        ds = self._open_csv(tmp_path)
        with pytest.raises(TypeError, match="numeric column"):
            self.plugin.run(
                "tabular.pair.correlation", ds, column_a="val", column_b="cat"
            )

    def _assert_valid_result(
        self, result: CapabilityResult, expected_type: str, expected_scope: ScopeKind
    ) -> None:
        assert isinstance(result, CapabilityResult)
        assert len(result.measurements) == 1
        msr = result.measurements[0]
        assert msr.type == expected_type
        assert msr.scope.kind == expected_scope
        assert msr.id.startswith("msr-")


# ── TestNullSentinels ─────────────────────────────────────────────────────────


class TestNullSentinels:
    """Verify that null_sentinels affect type inference, missing count, and params."""

    def _csv_with_sentinels(self, tmp_path: Path) -> Path:
        """CSV where 'score' column has sentinel strings that should become null."""
        content = (
            "id,score,label\n"
            "1,85.0,pass\n2,N/A,fail\n3,,pass\n4,92.0,pass\n5,NA,fail\n"
        )
        p = tmp_path / "sentinels.csv"
        p.write_text(content, encoding="utf-8")
        return p

    def test_sentinels_recognized_as_null(self, tmp_path: Path) -> None:
        plugin = TabularPlugin()
        p = self._csv_with_sentinels(tmp_path)
        ds = plugin.open(Source(paths=(p,)))
        result = plugin.run("tabular.column.missing", ds, column="score")
        payload = dict(result.measurements[0].payload)
        assert payload["total_count"] == 5
        assert payload["missing_count"] == 3  # N/A, '', NA all become null
        assert abs(payload["missing_proportion"] - 0.6) < 1e-9  # type: ignore[arg-type]

    def test_sentinels_enable_numeric_inference(self, tmp_path: Path) -> None:
        """Column mixing floats with sentinel strings must be inferred as float64."""
        plugin = TabularPlugin()
        p = self._csv_with_sentinels(tmp_path)
        ds = plugin.open(Source(paths=(p,)))
        dtype = ds.column_dtype("score")
        # With sentinels converted to null, Arrow infers float64
        assert dtype in {"float", "float16", "float32", "float64", "double"}

    def test_missing_params_record_sentinels(self, tmp_path: Path) -> None:
        plugin = TabularPlugin()
        p = self._csv_with_sentinels(tmp_path)
        ds = plugin.open(Source(paths=(p,)))
        result = plugin.run("tabular.column.missing", ds, column="score")
        prov = result.measurements[0].provenance
        assert "null_sentinels" in prov.params
        sentinels = prov.params["null_sentinels"]
        assert "" in sentinels  # type: ignore[operator]
        assert "N/A" in sentinels  # type: ignore[operator]

    def test_custom_sentinels_override_default(self, tmp_path: Path) -> None:
        """Plugin with empty sentinels tuple should not convert N/A to null."""
        plugin_no_sentinels = TabularPlugin(null_sentinels=())
        p = self._csv_with_sentinels(tmp_path)
        ds = plugin_no_sentinels.open(Source(paths=(p,)))
        result = plugin_no_sentinels.run("tabular.column.missing", ds, column="score")
        payload = dict(result.measurements[0].payload)
        # Without sentinels N/A and '' stay as-is, column stays string → 0 nulls
        assert payload["missing_count"] == 0

    def test_different_sentinels_different_msr_id(self, tmp_path: Path) -> None:
        """Changing null_sentinels rotates the measurement id."""
        plugin_default = TabularPlugin()
        plugin_custom = TabularPlugin(null_sentinels=("MISSING",))
        p = self._csv_with_sentinels(tmp_path)
        ds_default = plugin_default.open(Source(paths=(p,)))
        ds_custom = plugin_custom.open(Source(paths=(p,)))
        r_default = plugin_default.run(
            "tabular.column.missing", ds_default, column="score"
        )
        r_custom = plugin_custom.run(
            "tabular.column.missing", ds_custom, column="score"
        )
        assert r_default.measurements[0].id != r_custom.measurements[0].id


# ── TestFrequencyPayloadTypes ─────────────────────────────────────────────────


class TestFrequencyPayloadTypes:
    """Verify frequency payload values are JSON-serialisable (no Python reprs)."""

    def test_date_values_are_iso_strings(self) -> None:
        col = pa.array(
            [
                datetime.date(2024, 1, 15),
                datetime.date(2024, 1, 15),
                datetime.date(2024, 3, 1),
            ],
            type=pa.date32(),
        )
        r = compute_frequency(col)
        for entry in r["frequencies"]:
            val = entry["value"]
            assert isinstance(val, str), f"Expected str, got {type(val)}"
            datetime.date.fromisoformat(val)  # type: ignore[arg-type]

    def test_datetime_values_are_iso_strings(self) -> None:
        col = pa.array(
            [
                datetime.datetime(2024, 1, 15, 10, 30),  # noqa: DTZ001
                datetime.datetime(2024, 1, 15, 10, 30),  # noqa: DTZ001
            ],
            type=pa.timestamp("us"),
        )
        r = compute_frequency(col)
        for entry in r["frequencies"]:
            assert isinstance(entry["value"], str)

    def test_float_nan_becomes_string(self) -> None:
        col = pa.array([float("nan"), float("nan"), 1.0], type=pa.float64())
        r = compute_frequency(col)
        values = [e["value"] for e in r["frequencies"]]
        assert "NaN" in values

    def test_bytes_become_hex_string(self) -> None:
        col = pa.array([b"\xde\xad", b"\xbe\xef", b"\xde\xad"], type=pa.binary())
        r = compute_frequency(col)
        for entry in r["frequencies"]:
            assert isinstance(entry["value"], str)

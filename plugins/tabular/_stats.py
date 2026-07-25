"""Statistical computations for tabular columns.

All functions accept pyarrow arrays and return plain dicts that conform to the
corresponding measurement JSON Schema.  Null handling: Arrow nulls are dropped
before numeric computations; float NaN is also treated as missing for normality
and correlation (consistent with pairwise-deletion semantics).
"""

from __future__ import annotations

import datetime
import decimal
import math
from typing import Final

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
from scipy import stats

__all__ = [
    "compute_correlation",
    "compute_descriptive",
    "compute_frequency",
    "compute_missing",
    "compute_normality",
    "compute_uniqueness",
]

_NORMALITY_MIN_N: Final = 3
_CORRELATION_MIN_N: Final = 2

# ── helpers ───────────────────────────────────────────────────────────────────


def _to_float64(
    array: pa.Array | pa.ChunkedArray,
) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
    """Drop Arrow-nulls and return a float64 numpy array (NaN preserved)."""
    return np.asarray(array.drop_null(), dtype=np.float64)


def _valid_float64(
    array: pa.Array | pa.ChunkedArray,
) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
    """Drop Arrow-nulls AND float NaN, return float64 numpy array."""
    arr = _to_float64(array)
    return arr[~np.isnan(arr)]


def _to_payload_value(v: object) -> object:  # noqa: PLR0911, C901
    """Convert pyarrow .as_py() value to a JSON-serialisable form."""
    if v is None or isinstance(v, bool | int | str):
        return v
    if isinstance(v, float):
        if math.isnan(v):
            return "NaN"
        if math.isinf(v):
            return "+Inf" if v > 0 else "-Inf"
        return v
    if isinstance(v, datetime.datetime):
        return v.isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, datetime.time):
        return v.isoformat()
    if isinstance(v, datetime.timedelta):
        return int(v / datetime.timedelta(microseconds=1))
    if isinstance(v, bytes):
        return v.hex()
    if isinstance(v, decimal.Decimal):
        return str(v)
    return str(v)


# ── six capabilities ──────────────────────────────────────────────────────────


def compute_missing(
    column: pa.Array | pa.ChunkedArray,
) -> dict[str, object]:
    """Count Arrow-null values and their proportion."""
    total = len(column)
    null_count = column.null_count
    proportion = null_count / total if total > 0 else 0.0
    return {
        "total_count": total,
        "missing_count": null_count,
        "missing_proportion": proportion,
    }


def compute_descriptive(
    column: pa.Array | pa.ChunkedArray,
) -> dict[str, object]:
    """Descriptive statistics (nulls dropped, quartile method=linear, ddof=1).

    skewness: Fisher-Pearson standardised 3rd moment, requires count >= 3.
    excess_kurtosis: Fisher definition (kurtosis - 3), requires count >= 4.
    Both are sample-size independent and serve as effect-size measures for the
    distribution_shape Finding rule; see docs/DECISIONS.md for threshold sources.
    """
    arr = _to_float64(column)
    if len(arr) == 0:
        raise ValueError("Cannot compute descriptive statistics on a fully-null column")
    result: dict[str, object] = {
        "count": len(arr),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "q25": float(np.quantile(arr, 0.25, method="linear")),
        "q50": float(np.quantile(arr, 0.50, method="linear")),
        "q75": float(np.quantile(arr, 0.75, method="linear")),
        "null_count": column.null_count,
    }
    if len(arr) >= 3:
        result["skewness"] = float(stats.skew(arr))
    if len(arr) >= 4:
        result["excess_kurtosis"] = float(stats.kurtosis(arr))
    return result


def compute_frequency(
    column: pa.Array | pa.ChunkedArray,
) -> dict[str, object]:
    """Frequency distribution (nulls excluded; temporals → ISO strings)."""
    total = len(column)
    null_count = column.null_count
    valid = column.drop_null()
    valid_count = len(valid)

    vc = pc.value_counts(valid)
    # value_counts returns a StructArray with fields "values" and "counts"
    py_values = [_to_payload_value(v) for v in vc.field("values").to_pylist()]
    py_counts = vc.field("counts").to_pylist()
    items = sorted(
        zip(py_values, py_counts, strict=False), key=lambda x: x[1], reverse=True
    )

    frequencies: list[dict[str, object]] = []
    for value, cnt in items:
        n = int(cnt)
        proportion = n / valid_count if valid_count > 0 else 0.0
        frequencies.append({"value": value, "count": n, "proportion": proportion})

    result: dict[str, object] = {
        "total_count": total,
        "frequencies": frequencies,
    }
    if null_count > 0:
        result["null_count"] = null_count
    return result


def compute_uniqueness(
    column: pa.Array | pa.ChunkedArray,
) -> dict[str, object]:
    """Uniqueness metrics.

    total_count is total rows including nulls — consistent with core.quality.missing.
    unique_proportion is unique_count / non-null count.
    null_count is emitted only when > 0.
    """
    total = len(column)
    null_count = column.null_count
    valid = column.drop_null()
    valid_count = len(valid)
    unique = len(pc.unique(valid))
    duplicate = valid_count - unique
    proportion = unique / valid_count if valid_count > 0 else 0.0
    result: dict[str, object] = {
        "total_count": total,
        "unique_count": unique,
        "duplicate_count": duplicate,
        "unique_proportion": proportion,
    }
    if null_count > 0:
        result["null_count"] = null_count
    return result


def compute_normality(
    column: pa.Array | pa.ChunkedArray,
    *,
    n_cutoff: int = 5000,
) -> dict[str, object]:
    """Normality test driven by n_cutoff.

    n <= n_cutoff → Shapiro-Wilk; n > n_cutoff → D'Agostino-Pearson.
    Arrow-nulls and float NaN are both excluded.
    n_cutoff must be passed by the caller and recorded in provenance params.
    """
    arr = _valid_float64(column)
    n = len(arr)
    if n < _NORMALITY_MIN_N:
        raise ValueError(f"Normality test requires at least 3 valid values, got {n}")

    if n <= n_cutoff:
        stat, p = stats.shapiro(arr)
        test_name = "shapiro_wilk"
    else:
        stat, p = stats.normaltest(arr)
        test_name = "dagostino_pearson"

    return {
        "test": test_name,
        "statistic": float(stat),
        "p_value": float(p),
        "sample_size": n,
    }


def compute_correlation(
    col_a: pa.Array | pa.ChunkedArray,
    col_b: pa.Array | pa.ChunkedArray,
    method: str = "pearson",
) -> dict[str, object]:
    """Pairwise correlation between two numeric columns (pairwise deletion)."""
    if len(col_a) != len(col_b):
        raise ValueError(
            f"Columns must have the same length, got {len(col_a)} and {len(col_b)}"
        )

    mask = pc.and_(pc.is_valid(col_a), pc.is_valid(col_b))
    a_valid = np.asarray(col_a.filter(mask), dtype=np.float64)
    b_valid = np.asarray(col_b.filter(mask), dtype=np.float64)

    nan_mask = ~(np.isnan(a_valid) | np.isnan(b_valid))
    arr_a = a_valid[nan_mask]
    arr_b = b_valid[nan_mask]

    n = len(arr_a)
    if n < _CORRELATION_MIN_N:
        raise ValueError(
            f"Correlation requires at least 2 paired observations, got {n}"
        )

    if method == "pearson":
        result = stats.pearsonr(arr_a, arr_b)
    elif method == "spearman":
        result = stats.spearmanr(arr_a, arr_b)
    elif method == "kendall":
        result = stats.kendalltau(arr_a, arr_b)
    else:
        raise ValueError(f"Unknown correlation method: {method!r}")

    return {
        "method": method,
        "coefficient": float(result.statistic),
        "p_value": float(result.pvalue),
        "sample_size": n,
    }

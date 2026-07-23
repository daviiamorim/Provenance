"""Statistical computations for tabular columns.

All functions accept pyarrow arrays and return plain dicts that conform to the
corresponding measurement JSON Schema.  Null handling: Arrow nulls are dropped
before numeric computations; float NaN is also treated as missing for normality
and correlation (consistent with pairwise-deletion semantics).
"""

from __future__ import annotations

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

# Normality regime cutoff: Shapiro-Wilk for N ≤ this value, D'Agostino-Pearson above.
_SHAPIRO_MAX_N: Final = 5000
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
    """Descriptive statistics (nulls dropped, quartile method=linear, ddof=1)."""
    arr = _to_float64(column)
    if len(arr) == 0:
        raise ValueError("Cannot compute descriptive statistics on a fully-null column")
    return {
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


def compute_frequency(
    column: pa.Array | pa.ChunkedArray,
) -> dict[str, object]:
    """Frequency distribution for a column (nulls excluded from proportions)."""
    total = len(column)
    null_count = column.null_count
    valid = column.drop_null()
    valid_count = len(valid)

    vc = pc.value_counts(valid)
    # value_counts returns a StructArray with fields "values" and "counts"
    py_values = vc.field("values").to_pylist()
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
    """Uniqueness metrics over non-null values."""
    valid = column.drop_null()
    total = len(valid)  # schema: total_count = non-null count
    unique = len(pc.unique(valid))
    duplicate = total - unique
    proportion = unique / total if total > 0 else 0.0
    return {
        "total_count": total,
        "unique_count": unique,
        "duplicate_count": duplicate,
        "unique_proportion": proportion,
    }


def compute_normality(
    column: pa.Array | pa.ChunkedArray,
) -> dict[str, object]:
    """Normality test: Shapiro-Wilk for N≤5000, D'Agostino-Pearson for N>5000.

    Arrow-nulls and float NaN are both treated as missing and excluded.
    """
    arr = _valid_float64(column)
    n = len(arr)
    if n < _NORMALITY_MIN_N:
        raise ValueError(f"Normality test requires at least 3 valid values, got {n}")

    if n <= _SHAPIRO_MAX_N:
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
    """Pairwise correlation between two numeric columns.

    Pairwise deletion: only rows where both columns are non-null AND non-NaN are
    used.  Supported methods: pearson, spearman, kendall.
    """
    if len(col_a) != len(col_b):
        raise ValueError(
            f"Columns must have the same length, got {len(col_a)} and {len(col_b)}"
        )

    # Pairwise deletion mask: both Arrow-valid
    mask = pc.and_(pc.is_valid(col_a), pc.is_valid(col_b))
    a_valid = np.asarray(col_a.filter(mask), dtype=np.float64)
    b_valid = np.asarray(col_b.filter(mask), dtype=np.float64)

    # Also drop rows where either has float NaN
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

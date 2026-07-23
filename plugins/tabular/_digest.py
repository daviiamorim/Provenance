"""Column digest — library-independent canonical representation for input provenance.

Format fed to SHA-256 (incremental, O(1) memory):
    {canonical_dtype_string}\\n
    {canonical_json(v1)}\\n
    {canonical_json(v2)}\\n
    null\\n              ← for None / Arrow-null values
    ...

This format is frozen. Changing it silently rotates all input_digest values and
breaks reproducibility. The anchor test in tests/test_tabular.py detects any drift.
"""

from __future__ import annotations

import datetime
import decimal
import hashlib
import math
from collections.abc import Iterator

import pyarrow as pa

from core.model import canonical_json

__all__ = ["canonical_dtype", "column_digest", "pair_digest"]


def canonical_dtype(arrow_type: pa.DataType) -> str:
    """Return the canonical string name for an Arrow DataType.

    Delegates to pyarrow's own str() representation, which follows the Arrow
    spec naming (e.g. "int64", "string", "timestamp[us, tz=UTC]").  These
    strings are stable within a major Arrow version and are what appears in
    Parquet metadata, making them safe to use as long-lived provenance keys.
    """
    return str(arrow_type)


def _to_canonical(py_val: object) -> object:  # noqa: C901, PLR0911, PLR0912
    """Convert a value returned by pyarrow's .as_py() to a canonical_json-safe form.

    Handles types that canonical_json doesn't natively accept (datetime, bytes,
    Decimal) by converting them to strings or ints.  NaN/Inf in floats are
    wrapped in a sentinel dict so they are distinct from both None and string "nan".
    """
    if py_val is None:
        return None
    if isinstance(py_val, bool):
        return py_val
    if isinstance(py_val, float):
        if math.isnan(py_val):
            return {"__special__": "nan"}
        if math.isinf(py_val):
            return {"__special__": "+inf" if py_val > 0 else "-inf"}
        # Mirror canonical_json's own float normalization rules
        normalized = 0.0 if py_val == -0.0 else py_val
        return int(normalized) if normalized == int(normalized) else normalized
    if isinstance(py_val, int):
        return py_val
    if isinstance(py_val, str):
        return py_val
    if isinstance(py_val, datetime.datetime):
        return py_val.isoformat()
    if isinstance(py_val, datetime.date):
        return py_val.isoformat()
    if isinstance(py_val, datetime.time):
        return py_val.isoformat()
    if isinstance(py_val, datetime.timedelta):
        # Total microseconds — unambiguous and lossless for Arrow duration types
        return int(py_val / datetime.timedelta(microseconds=1))
    if isinstance(py_val, bytes):
        return py_val.hex()
    if isinstance(py_val, decimal.Decimal):
        return str(py_val)
    if isinstance(py_val, list):
        return [_to_canonical(v) for v in py_val]
    if isinstance(py_val, dict):
        return {str(k): _to_canonical(v) for k, v in py_val.items()}
    return str(py_val)


def column_digest(dtype_str: str, values: Iterator[object]) -> str:
    """Compute a stable, library-independent digest for a column.

    Args:
        dtype_str: canonical dtype string from canonical_dtype().
        values: iterable of Python values (from pyarrow array.to_pylist() or
                equivalent).  None represents Arrow-null.

    Returns:
        Hex SHA-256 digest string.
    """
    h = hashlib.sha256()
    h.update(dtype_str.encode("utf-8") + b"\n")
    for v in values:
        h.update(canonical_json(_to_canonical(v)) + b"\n")
    return h.hexdigest()


def pair_digest(digest_a: str, digest_b: str) -> str:
    """Compute a symmetric digest for a pair of column digests.

    Order-independent: pair_digest(a, b) == pair_digest(b, a).
    Used as input_digest for correlation Measurements so that corr(A,B) and
    corr(B,A) share the same provenance digest.
    """
    return hashlib.sha256(canonical_json(sorted([digest_a, digest_b]))).hexdigest()

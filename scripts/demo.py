"""demo.py — inspect a CSV or Parquet file with TabularPlugin.

Usage:
    uv run python scripts/demo.py path/to/file.csv
    uv run python scripts/demo.py path/to/file.parquet
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.model import Measurement
from core.plugin import Source
from plugins.tabular import TabularPlugin
from plugins.tabular._plugin import _ColumnInfo

# ── display constants ─────────────────────────────────────────────────────────

_SEP = "-" * 72
_FREQ_PREVIEW = 3

# Arrow canonical names that correspond to numeric types we can do stats on.
_NUMERIC_DTYPES: frozenset[str] = frozenset({
    "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
    "float", "float16", "float32", "float64", "double",
    "decimal128", "decimal256",
})

# Maximum correlation pairs to display (avoids flooding on wide datasets).
_MAX_CORR_PAIRS = 6


def _is_numeric(col: _ColumnInfo) -> bool:
    return col.dtype_str in _NUMERIC_DTYPES


# ── formatting helpers ────────────────────────────────────────────────────────


def _fmt_float(v: object) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def _fmt_payload(payload: object) -> None:
    if not hasattr(payload, "items"):
        print(f"    {payload}")
        return
    for k, v in payload.items():  # type: ignore[union-attr]
        if isinstance(v, list):
            print(f"    {k}: [{len(v)} entries]")
            for item in v[:_FREQ_PREVIEW]:
                if isinstance(item, dict):
                    parts = "  ".join(
                        f"{ik}={iv:.6g}" if isinstance(iv, float)
                        else f"{ik}={iv!r}"
                        for ik, iv in item.items()
                    )
                    print(f"      {parts}")
                else:
                    print(f"      {item}")
            if len(v) > _FREQ_PREVIEW:
                print(f"      ... ({len(v) - _FREQ_PREVIEW} more)")
        elif isinstance(v, float):
            print(f"    {k}: {v:.6g}")
        else:
            print(f"    {k}: {v}")


def _print_measurement(msr: Measurement) -> None:
    print(f"  id        : {msr.id}")
    print(f"  type      : {msr.type}")
    scope = msr.scope
    print(f"  scope     : {scope.kind.value}  refs={scope.refs}")
    print("  payload   :")
    _fmt_payload(msr.payload)
    p = msr.provenance
    print("  provenance:")
    print(f"    producer     : {p.producer}  v{p.version}")
    if p.params:
        print(f"    params       : {dict(p.params)}")
    print(f"    input_digest : {p.input_digest[:24]}...")
    print(f"    duration_ms  : {p.duration_ms}")


def _run(plugin: TabularPlugin, ds: object, cap_id: str, **params: object) -> None:
    label = "  ".join(f"{k}={v!r}" for k, v in params.items())
    print()
    print(f"[{cap_id}]  {label}")
    try:
        result = plugin.run(cap_id, ds, **params)  # type: ignore[arg-type]
        _print_measurement(result.measurements[0])
    except Exception as exc:
        print(f"  SKIP: {exc}")


# ── main ──────────────────────────────────────────────────────────────────────


def _build_pairs(numeric_names: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    pairs.extend(
        (a, b)
        for i, a in enumerate(numeric_names)
        for b in numeric_names[i + 1:]
    )
    if len(numeric_names) == 1:
        pairs = [(numeric_names[0], numeric_names[0])]
    return pairs


def main() -> None:  # noqa: C901
    if len(sys.argv) != 2:  # noqa: PLR2004
        print(f"usage: python {sys.argv[0]} <file.csv|file.parquet>", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    plugin = TabularPlugin()
    source = Source(paths=(path,))

    # ── sniff ─────────────────────────────────────────────────────────────────
    sniff = plugin.sniff(source)
    print("=== sniff ===")
    print(f"  confidence : {sniff.confidence:.2f}")
    print(f"  evidence   : {sniff.evidence}")

    # ── open ──────────────────────────────────────────────────────────────────
    ds = plugin.open(source)
    print()
    print("=== dataset ===")
    print(f"  dataset_id : {ds.dataset_id}")
    for name, digest in ds.manifest():
        print(f"  {name}: sha256:{digest}")

    # ── schema ────────────────────────────────────────────────────────────────
    cols = ds.columns()
    print()
    print(f"=== columns ({len(cols)}) ===")
    for c in cols:
        tag = "numeric" if _is_numeric(c) else "string/other"
        print(f"  {c.name:<28} {c.dtype_str:<16} [{tag}]")

    numeric_cols = [c for c in cols if _is_numeric(c)]
    all_col_names = [c.name for c in cols]
    numeric_names = [c.name for c in numeric_cols]

    # ── per-column capabilities ───────────────────────────────────────────────
    print()
    print("=== capabilities ===")
    print(_SEP)

    for col_name in all_col_names:
        for cap_id in (
            "tabular.column.missing",
            "tabular.column.uniqueness",
            "tabular.column.frequency",
        ):
            _run(plugin, ds, cap_id, column=col_name)

    for col_name in numeric_names:
        for cap_id in (
            "tabular.column.descriptive",
            "tabular.column.normality",
        ):
            _run(plugin, ds, cap_id, column=col_name)

    # ── pairwise correlation ──────────────────────────────────────────────────
    pairs = _build_pairs(numeric_names)
    if pairs:
        if len(pairs) > _MAX_CORR_PAIRS:
            print()
            print(f"  (showing {_MAX_CORR_PAIRS} of {len(pairs)} correlation pairs)")
        for a, b in pairs[:_MAX_CORR_PAIRS]:
            _run(plugin, ds, "tabular.pair.correlation", column_a=a, column_b=b)

    print()
    print(_SEP)


if __name__ == "__main__":
    main()

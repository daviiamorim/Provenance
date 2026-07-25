"""demo.py — inspect a CSV or Parquet file with TabularPlugin.

Usage:
    uv run python scripts/demo.py path/to/file.csv
    uv run python scripts/demo.py path/to/file.parquet
"""

from __future__ import annotations

import sys
from pathlib import Path

# Force UTF-8 output so that Unicode characters in Finding statements
# (≥, ≤, é, etc.) are not mangled on Windows cp1252 terminals.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.composer import ReportResult, generate_report
from core.llm import StubLanguageModel
from core.model import Assessment, Finding, Measurement
from core.plugin import Source
from core.rules import RULE_REGISTRY
from plugins.tabular import TabularPlugin
from plugins.tabular._plugin import _ColumnInfo

# ── display constants ─────────────────────────────────────────────────────────

_SEP = "-" * 72
_FREQ_PREVIEW = 3

# Null sentinels recognised as missing values.  Passed to tabular.column.missing
# so that string representations of null (common in CSV exports) are not counted
# as present.  Adjust to match your dataset.
_NULL_SENTINELS: tuple[str, ...] = ("", "N/A", "NA", "n/a", "na", "-", "None", "none")

# Arrow canonical names that correspond to numeric types we can do stats on.
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

# Maximum correlation pairs to display (avoids flooding on wide datasets).
_MAX_CORR_PAIRS = 6

_SEV_TAG: dict[str, str] = {
    "ok": "[ OK  ]",
    "warn": "[WARN ]",
    "fail": "[FAIL ]",
}


def _is_numeric(col: _ColumnInfo) -> bool:
    return col.dtype_str in _NUMERIC_DTYPES


def _sev(sev: object) -> str:
    return _SEV_TAG.get(str(sev), f"[{sev}]")


# ── measurement formatting ────────────────────────────────────────────────────


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
                        f"{ik}={iv:.6g}" if isinstance(iv, float) else f"{ik}={iv!r}"
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


def _run(
    plugin: TabularPlugin, ds: object, cap_id: str, **params: object
) -> list[Measurement]:
    label = "  ".join(f"{k}={v!r}" for k, v in params.items())
    print()
    print(f"[{cap_id}]  {label}")
    try:
        result = plugin.run(cap_id, ds, **params)  # type: ignore[arg-type]
        _print_measurement(result.measurements[0])
        return list(result.measurements)
    except Exception as exc:
        print(f"  SKIP: {exc}")
        return []


# ── finding / assessment formatting ──────────────────────────────────────────


def _print_finding(f: Finding, msr_map: dict[str, Measurement]) -> None:
    print()
    print(f"[{f.type}]")
    print(f"  scope      : {f.scope.kind.value}  refs={f.scope.refs}")
    print(f"  {_sev(f.severity)}  {f.statement}")
    threshold_keys = [k for k in f.params if "threshold" in k or "cutoff" in k]
    if threshold_keys:
        parts = "  ".join(f"{k}={f.params[k]}" for k in sorted(threshold_keys))
        print(f"  thresholds : {parts}")
    if f.params.get("null_sentinels_applied"):
        print(f"  sentinels  : {f.params['null_sentinels_applied']}")
    print(f"  derived_from ({len(f.derived_from)} measurement(s)):")
    for msr_id in f.derived_from:
        msr = msr_map.get(msr_id)
        label = f"  ({msr.type})" if msr else ""
        print(f"    {msr_id}{label}")


def _print_assessment(a: Assessment, fnd_map: dict[str, Finding]) -> None:
    print()
    print(f"[{a.type}]")
    print(f"  goal    : {a.goal}")
    print(f"  verdict : {a.verdict}  {_sev(a.severity)}")
    print(f"  derived_from ({len(a.derived_from)} finding(s)):")
    for fnd_id in a.derived_from:
        fnd = fnd_map.get(fnd_id)
        if fnd:
            refs = fnd.scope.refs
            print(f"    {_sev(fnd.severity)} {fnd_id}  ({fnd.type}  refs={refs})")
        else:
            print(f"    {fnd_id}")


# ── claims report helpers ─────────────────────────────────────────────────────

_DEMO_RUN_ID = "run-demo" + "0" * 28


def _make_claim_sentence(f: Finding) -> str:
    """Return a demo Portuguese sentence citing f, numbers in Brazilian format."""
    col = f.scope.refs[0] if f.scope.refs else "dataset"
    if f.type == "core.finding.missing_rate":
        rate = float(f.params.get("missing_proportion", 0))
        pct_br = f"{rate * 100:.1f}".replace(".", ",")
        return f"A coluna {col} tem {pct_br}% de valores ausentes [{f.id}]."
    if f.type == "core.finding.duplicate_rate":
        rate = float(f.params.get("duplicate_proportion", 0))
        pct_br = f"{rate * 100:.1f}".replace(".", ",")
        return f"O dataset apresenta {pct_br}% de linhas duplicadas [{f.id}]."
    return f"Foi identificado achado '{f.type.split('.')[-1]}' [{f.id}]."


def _print_claims_report(result: ReportResult) -> None:
    m = result.metrics
    print(f"  total sentences : {m.total_sentences}")
    print(f"  claims approved : {len(result.claims)}")
    print(f"  discarded       : {m.discarded}  (discard rate {m.discard_rate:.1%})")
    rates = m.rejection_rate_by_layer
    print(
        f"  rejection rates : syntactic={rates['syntactic']:.1%}"
        f"  numeric={rates['numeric']:.1%}"
        f"  semantic={rates['semantic']:.1%}"
    )
    if result.claims:
        print()
        print("  Claims:")
        for clm in result.claims:
            a_count = clm.validation.attempts
            tag = f"  (attempt {a_count})" if a_count > 1 else ""
            print(f"    [{clm.id[:16]}…] {clm.text}{tag}")
    if result.rejected:
        print()
        print("  Rejected:")
        for r in result.rejected:
            snippet = repr(r.text[:55])
            print(
                f"    [attempt {r.attempt}] [{r.layer.value}]"
                f" {r.reason_code}: {snippet}"
            )


# ── main ──────────────────────────────────────────────────────────────────────


def _build_pairs(numeric_names: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    pairs.extend(
        (a, b) for i, a in enumerate(numeric_names) for b in numeric_names[i + 1 :]
    )
    if len(numeric_names) == 1:
        pairs = [(numeric_names[0], numeric_names[0])]
    return pairs


def main() -> None:  # noqa: C901, PLR0912, PLR0915
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

    all_measurements: list[Measurement] = []

    for col_name in all_col_names:
        all_measurements.extend(
            _run(
                plugin,
                ds,
                "tabular.column.missing",
                column=col_name,
                null_sentinels=_NULL_SENTINELS,
            )
        )
        for cap_id in ("tabular.column.uniqueness", "tabular.column.frequency"):
            all_measurements.extend(_run(plugin, ds, cap_id, column=col_name))

    for col_name in numeric_names:
        for cap_id in ("tabular.column.descriptive", "tabular.column.normality"):
            all_measurements.extend(_run(plugin, ds, cap_id, column=col_name))

    # ── dataset-level capabilities ────────────────────────────────────────────
    all_measurements.extend(_run(plugin, ds, "tabular.dataset.row_dedup"))

    # ── pairwise correlation ──────────────────────────────────────────────────
    pairs = _build_pairs(numeric_names)
    if pairs:
        if len(pairs) > _MAX_CORR_PAIRS:
            print()
            print(f"  (showing {_MAX_CORR_PAIRS} of {len(pairs)} correlation pairs)")
        for a, b in pairs[:_MAX_CORR_PAIRS]:
            all_measurements.extend(
                _run(plugin, ds, "tabular.pair.correlation", column_a=a, column_b=b)
            )

    # ── note: skipped columns ─────────────────────────────────────────────────
    non_numeric = [c for c in cols if not _is_numeric(c)]
    if non_numeric:
        print()
        print("NOTE — the following columns were not analysed by numeric capabilities")
        print("       (descriptive, normality, correlation) because Arrow inferred")
        print("       them as non-numeric types:")
        for c in non_numeric:
            print(f"  {c.name:<28} {c.dtype_str}")
        print()
        print("  If any of these should be numeric but contain sentinel strings")
        print("  such as 'N/A', 'NA', or '' for missing values, re-open with")
        print("  custom null_sentinels:")
        print("    plugin = TabularPlugin(null_sentinels=('', 'N/A', 'NA', ...))")

    # ── findings ──────────────────────────────────────────────────────────────
    print()
    print(_SEP)
    print()
    print("=== findings ===")
    print(_SEP)

    msr_map = {m.id: m for m in all_measurements}
    all_findings = RULE_REGISTRY.run_findings(ds.dataset_id, all_measurements)

    if not all_findings:
        print(
            "  (no findings produced"
            " — check that measurements cover the required types)"
        )
    else:
        severity_order = {"fail": 0, "warn": 1, "ok": 2}
        for finding in sorted(
            all_findings,
            key=lambda f: (
                severity_order.get(str(f.severity), 9),
                f.type,
                f.scope.refs,
            ),
        ):
            _print_finding(finding, msr_map)

    # ── assessments ───────────────────────────────────────────────────────────
    print()
    print(_SEP)
    print()
    print("=== assessments ===")
    print(_SEP)

    fnd_map = {f.id: f for f in all_findings}
    all_assessments: list[Assessment] = []
    any_assessment = False
    for goal in ("data_quality", "modeling_readiness"):
        assessments = RULE_REGISTRY.run_assessments(ds.dataset_id, goal, all_findings)
        all_assessments.extend(assessments)
        for assessment in assessments:
            _print_assessment(assessment, fnd_map)
            any_assessment = True
    if not any_assessment:
        print(
            "  (no assessments produced — findings must include at least one "
            "relevant type per goal)"
        )

    # ── claims report ─────────────────────────────────────────────────────────
    print()
    print(_SEP)
    print()
    print("=== claims report ===")
    print(_SEP)

    fail_findings = [f for f in all_findings if str(f.severity) in ("fail", "warn")]
    stub_sentences = [_make_claim_sentence(f) for f in fail_findings[:6]]
    stub_sentences.extend(
        f"A avaliação de {a.goal} resultou em situação {a.verdict} [{a.id}]."
        for a in all_assessments[:2]
    )

    if stub_sentences:
        stub_text = " ".join(stub_sentences)
        report = generate_report(
            findings=all_findings,
            assessments=all_assessments,
            composer_model=StubLanguageModel([stub_text]),
            judge_model=StubLanguageModel(["entailed"] * 50),
            run_id=_DEMO_RUN_ID,
            dataset_id=ds.dataset_id,
        )
        _print_claims_report(report)
    else:
        print("  (no fail/warn findings — nothing to claim)")

    print()
    print(_SEP)


if __name__ == "__main__":
    main()

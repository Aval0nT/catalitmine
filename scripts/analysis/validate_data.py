"""
validate_data.py — is the table-derived dataset actually usable? (no LLM)

Loads data/05_normalized/catalyst_records_*.jsonl, builds a numeric feature
matrix, and asks three questions:
  1. DENSITY  — which attributes are dense enough to model?
  2. JOINABILITY — how many records support condition→performance or
     structure→activity analysis (have features on both sides)?
  3. SIGNAL   — do any interpretable pairwise correlations emerge?

This is a go/no-go check on the pipeline, not a final analysis. It deliberately
coalesces only same-quantity spelling variants (co2_conv + co2_conversion_pct,
s_bet + bet_surface_area) and never merges across reactions (CO2 conversion vs
methanol conversion stay separate).

Usage:  python3 scripts/analysis/validate_data.py
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
NORM = ROOT / "data" / "05_normalized"
OUT  = ROOT / "outputs" / "reports"

# Coalesce ONLY unambiguous same-quantity spelling variants.
COALESCE = {
    "co2_conversion_pct":      ["co2_conversion_pct", "co2_conv"],
    "co_conversion_pct":       ["co_conversion_pct", "co_conv"],
    "methanol_conversion_pct": ["methanol_conversion_pct", "meoh_conversion_pct"],
    "bet_surface_area":        ["bet_surface_area", "s_bet"],
    "total_acidity":           ["total_acidity", "c_as"],
}

# Feature groups for joinability analysis.
GROUPS = {
    "conditions":  ["temperature_c", "pressure", "whsv", "ghsv",
                    "contact_time", "h2_co2_ratio", "h2_co_ratio"],
    "texture":     ["bet_surface_area", "total_pore_volume", "micropore_volume",
                    "external_surface_area", "crystallinity_pct"],
    "acidity":     ["total_acidity", "bronsted_acidity", "lewis_acidity",
                    "weak_acidity", "strong_acidity", "bas_las_ratio"],
    "composition": ["si_al_ratio", "metal_loading_wt"],
    "performance": ["co2_conversion_pct", "co_conversion_pct",
                    "methanol_conversion_pct", "conversion_pct", "selectivity_pct",
                    "aromatics_selectivity_pct", "btx_selectivity_pct",
                    "olefin_selectivity_pct", "methanol_selectivity_pct",
                    "space_time_yield", "yield_pct", "aromatics_yield_pct",
                    # per-species product percentages are performance metrics too
                    "benzene_pct", "toluene_pct", "xylenes_pct",
                    "total_aromatics_pct", "btx_pct", "methane_pct",
                    "ethylene_pct", "propylene_pct", "light_olefins_pct",
                    "paraffins_pct"],
}
ALL_FEATURES = [f for fs in GROUPS.values() for f in fs]


def load_records() -> list[dict]:
    files = sorted(glob.glob(str(NORM / "catalyst_records_*.jsonl")))
    if not files:
        raise SystemExit("no catalyst_records_*.jsonl — run build_catalyst_records.py")
    recs = [json.loads(l) for l in open(files[-1], encoding="utf-8")]
    print(f"loaded {len(recs)} records from {Path(files[-1]).name}\n")
    return recs


def to_frame(recs: list[dict]) -> pd.DataFrame:
    """One row per record; numeric attribute values only, coalesced."""
    alias = {}
    for canon, variants in COALESCE.items():
        for v in variants:
            alias[v] = canon
    rows = []
    for r in recs:
        row = {"paper_doi": r["paper_doi"], "catalyst": r["catalyst_label"]}
        for attr, meta in r["attributes"].items():
            if not meta.get("numeric"):
                continue
            key = alias.get(attr, attr)
            # first non-null wins (don't clobber a coalesced value)
            if key not in row or pd.isna(row.get(key)):
                row[key] = meta["value"]
        rows.append(row)
    return pd.DataFrame(rows)


def report_density(df: pd.DataFrame) -> None:
    n = len(df)
    print("=" * 64)
    print(f"DENSITY — {n} records")
    print("=" * 64)
    present = [(c, df[c].notna().sum()) for c in df.columns
               if c not in ("paper_doi", "catalyst")]
    present.sort(key=lambda x: -x[1])
    for c, k in present[:24]:
        grp = next((g for g, fs in GROUPS.items() if c in fs), "")
        bar = "#" * int(40 * k / n)
        print(f"  {100*k/n:5.1f}% {k:4d}  {c:28s} {grp:11s} {bar}")


def report_joinability(df: pd.DataFrame) -> None:
    n = len(df)
    def has_any(cols):
        cols = [c for c in cols if c in df.columns]
        if not cols:
            return pd.Series([False] * n)
        return df[cols].notna().any(axis=1)
    cond = has_any(GROUPS["conditions"])
    perf = has_any(GROUPS["performance"])
    struct = has_any(GROUPS["texture"] + GROUPS["acidity"] + GROUPS["composition"])
    print("\n" + "=" * 64)
    print("JOINABILITY — records supporting an analysis")
    print("=" * 64)
    print(f"  condition + performance : {(cond & perf).sum():4d}  "
          "(what conditions drive performance)")
    print(f"  structure + performance : {(struct & perf).sum():4d}  "
          "(structure–activity — the ML goal)")
    print(f"  structure + condition + performance: {(struct & cond & perf).sum():4d}  "
          "(full record)")


def report_correlations(df: pd.DataFrame, min_overlap: int = 15) -> None:
    feats = [c for c in ALL_FEATURES if c in df.columns and df[c].notna().sum() >= 10]
    num = df[feats].apply(pd.to_numeric, errors="coerce")
    print("\n" + "=" * 64)
    print(f"SIGNAL — pairwise correlations (≥{min_overlap} co-occurring records)")
    print("=" * 64)
    found = []
    for i, a in enumerate(feats):
        for b in feats[i + 1:]:
            pair = num[[a, b]].dropna()
            if len(pair) < min_overlap:
                continue
            if pair[a].nunique() < 2 or pair[b].nunique() < 2:
                continue   # constant column → undefined correlation
            r = pair[a].corr(pair[b])
            if pd.notna(r) and abs(r) >= 0.30:
                found.append((abs(r), r, a, b, len(pair)))
    found.sort(reverse=True)
    if not found:
        print("  no pairwise |r| ≥ 0.30 with enough overlap — data too sparse "
              "or no linear signal yet.")
    for _, r, a, b, k in found[:20]:
        print(f"  r={r:+.2f}  n={k:3d}   {a}  ×  {b}")


def main() -> None:
    recs = load_records()
    df = to_frame(recs)
    report_density(df)
    report_joinability(df)
    report_correlations(df)
    OUT.mkdir(parents=True, exist_ok=True)
    # save the feature matrix for inspection / downstream
    keep = ["paper_doi", "catalyst"] + [c for c in ALL_FEATURES if c in df.columns]
    out_csv = OUT / "feature_matrix.csv"
    df[keep].to_csv(out_csv, index=False)
    print(f"\nfeature matrix → {out_csv}")


if __name__ == "__main__":
    main()

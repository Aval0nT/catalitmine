"""
analyze_co2_window.py — first real analysis: CO2->aromatics condition–performance.

Goal: a process-window look at CO2 hydrogenation to aromatics, and a direct test
of whether the pooled pressure x conversion = -0.58 correlation seen in
validate_data is a real trend or a mixed-population (Simpson) artifact.

Honest scope note printed at run time: the analyzable condition–performance data
currently comes from review summary tables, so this is an analysis of curated
review data, not independent multi-paper extraction. Units are normalised
(temperatures stored in K are converted to deg C).

No LLM. Output: console report + figures/co2_pressure_stratified.png
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
NORM = ROOT / "data" / "05_normalized"
DB   = ROOT / "db" / "catalysis.db"
FIG  = ROOT / "figures"


def latest_records() -> list[dict]:
    f = sorted(NORM.glob("catalyst_records_*.jsonl"))[-1]
    return [json.loads(l) for l in open(f, encoding="utf-8")]


def num(rec: dict, *keys):
    for k in keys:
        a = rec["attributes"].get(k)
        if a and a.get("numeric"):
            return a["value"]
    return None


def norm_temp_c(t):
    """Reaction temps are ~200-450 deg C (=473-723 K). Values >500 are Kelvin."""
    if t is None:
        return None
    return round(t - 273.15, 1) if t > 500 else t


def family(label: str) -> str:
    s = label.lower()
    if "fe" in s:                              return "Fe-based"
    if "zn" in s and "zr" in s:                return "ZnZrOx"
    if "zn" in s and "cr" in s:                return "ZnCrOx"
    if ("in" in s and "zr" in s) or "in2o3" in s: return "InOx/InZr"
    if "ga" in s:                              return "Ga-based"
    if "cu" in s:                              return "Cu-based"
    if "zn" in s:                              return "Zn-based"
    return "other"


def build_df() -> pd.DataFrame:
    recs = latest_records()
    conn = sqlite3.connect(DB)
    topic = {d: t for d, t in conn.execute("SELECT doi,topic FROM papers")}
    conn.close()
    rows = []
    for r in recs:
        doi = r["paper_doi"]
        conv = num(r, "co2_conversion_pct", "co2_conv")
        if topic.get(doi) != "co2a" and conv is None:
            continue
        rows.append({
            "paper": doi,
            "catalyst": r["catalyst_label"],
            "family": family(r["catalyst_label"]),
            "T_C": norm_temp_c(num(r, "temperature_c")),
            "P_MPa": num(r, "pressure"),
            "co2_conv": conv,
            "selectivity": num(r, "selectivity_pct"),
            "STY": num(r, "space_time_yield"),
        })
    return pd.DataFrame(rows)


def corr(df, a, b):
    pair = df[[a, b]].dropna()
    if len(pair) < 5 or pair[a].nunique() < 2 or pair[b].nunique() < 2:
        return None, len(pair)
    return round(pair[a].corr(pair[b]), 2), len(pair)


def main() -> None:
    df = build_df()
    print("=" * 70)
    print("CO2->aromatics — condition–performance (first analysis)")
    print("=" * 70)
    print(f"records in CO2 subset: {len(df)}")
    print("source papers (all review summary tables — see scope note):")
    for p, n in df["paper"].value_counts().items():
        print(f"   {n:3d}  {p}")

    cp = df.dropna(subset=["co2_conv"])
    print(f"\nwith CO2 conversion: {len(cp)} | +T: {cp['T_C'].notna().sum()} | "
          f"+P: {cp['P_MPa'].notna().sum()}")

    # ---- Pressure stratification test --------------------------------------
    print("\n" + "-" * 70)
    print("PRESSURE × CO2-CONVERSION — is the negative trend real or pooled artifact?")
    print("-" * 70)
    r_all, n_all = corr(cp, "P_MPa", "co2_conv")
    print(f"  pooled (all sources)      : r={r_all}  n={n_all}")
    print("  within each source paper:")
    for p, sub in cp.groupby("paper"):
        r, n = corr(sub, "P_MPa", "co2_conv")
        print(f"     r={str(r):>5}  n={n:3d}   {p}")
    print("  within each catalyst family (n>=8):")
    for fam, sub in cp.groupby("family"):
        r, n = corr(sub, "P_MPa", "co2_conv")
        if n >= 8:
            print(f"     r={str(r):>5}  n={n:3d}   {fam}")

    # ---- Process window ----------------------------------------------------
    print("\n" + "-" * 70)
    print("PROCESS WINDOW — mean CO2 conversion by temperature × pressure bin")
    print("-" * 70)
    w = cp.dropna(subset=["T_C", "P_MPa"]).copy()
    if len(w):
        w["T_bin"] = pd.cut(w["T_C"], [200, 300, 350, 400, 700],
                            labels=["200–300", "300–350", "350–400", ">400"])
        w["P_bin"] = pd.cut(w["P_MPa"], [0, 1, 3, 6],
                            labels=["≤1 MPa", "1–3 MPa", "3–6 MPa"])
        piv = w.pivot_table(values="co2_conv", index="T_bin", columns="P_bin",
                            aggfunc="mean", observed=False)
        cnt = w.pivot_table(values="co2_conv", index="T_bin", columns="P_bin",
                            aggfunc="count", observed=False)
        print("mean CO2 conversion (%):")
        print(piv.round(1).to_string())
        print("\n(n per cell:)")
        print(cnt.fillna(0).astype(int).to_string())
        best = w.loc[w["co2_conv"].idxmax()]
        print(f"\nhighest single CO2 conversion: {best['co2_conv']:.1f}% at "
              f"{best['T_C']:.0f} °C, {best['P_MPa']:.1f} MPa "
              f"({best['family']}, {best['catalyst'][:28]})")

    # ---- Figure ------------------------------------------------------------
    FIG.mkdir(parents=True, exist_ok=True)
    import numpy as np
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    pp = cp.dropna(subset=["P_MPa", "co2_conv"])
    # pooled trend (the misleading one)
    z = np.polyfit(pp["P_MPa"], pp["co2_conv"], 1)
    xs = np.linspace(pp["P_MPa"].min(), pp["P_MPa"].max(), 50)
    ax.plot(xs, np.polyval(z, xs), "k--", lw=2,
            label=f"pooled (r={r_all}) — misleading")
    for fam, sub in pp.groupby("family"):
        pts = ax.scatter(sub["P_MPa"], sub["co2_conv"], alpha=0.7, s=40,
                         label=f"{fam} (n={len(sub)})")
        # per-family trend only where pressure actually varies and n>=8
        if len(sub) >= 8 and sub["P_MPa"].nunique() >= 3 \
           and (sub["P_MPa"].max() - sub["P_MPa"].min()) >= 1:
            r, _ = corr(sub, "P_MPa", "co2_conv")
            zf = np.polyfit(sub["P_MPa"], sub["co2_conv"], 1)
            ax.plot(xs, np.polyval(zf, xs), lw=1.6, color=pts.get_facecolor()[0],
                    label=f"   ↳ {fam} trend (r={r})")
    ax.set_ylim(0, 62)
    ax.set_xlabel("Pressure (MPa)")
    ax.set_ylabel("CO$_2$ conversion (%)")
    ax.set_title("CO$_2$ conversion vs pressure — Simpson's paradox\n"
                 "pooled trend is negative; per-family trends diverge")
    ax.legend(fontsize=7.5, loc="upper right")
    fig.tight_layout()
    out = FIG / "co2_pressure_stratified.png"
    fig.savefig(out, dpi=130)
    print(f"\nfigure → {out}")

    print("\n" + "=" * 70)
    print("SCOPE NOTE: condition–performance data here is from 2 review summary")
    print("tables, not independent primary-paper extraction. Treat as a method")
    print("demonstration; robust windows need primary-paper SI/figure data.")
    print("=" * 70)


if __name__ == "__main__":
    main()

"""
CO2-to-Aromatics Visualization
================================
Fig 1 — Heatmap: active_metal × zeolite_type → mean aromatic selectivity
Fig 2 — Heatmap: active_metal × support → mean CO2 conversion
Fig 3 — Scatter: temperature × aromatic selectivity, coloured by catalyst group

Usage:
  python3 scripts/analysis/visualize_co2_heatmap.py [--out figures/]
"""

from __future__ import annotations
import argparse
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB   = ROOT / "db" / "catalysis.db"

# ── Load ──────────────────────────────────────────────────────────────────────

def load_co2_data() -> pd.DataFrame:
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query(
        """
        SELECT  e.active_metal,
                e.support,
                e.zeolite_type,
                e.catalyst_system,
                e.metal_loading_wt,
                e.methanol_conv_pct   AS co2_conv_pct,
                e.aromatic_sel_pct,
                e.btx_sel_pct,
                e.olefin_pct,
                e.propylene_pct,
                e.temperature_c,
                e.pressure_mpa,
                e.tos_h,
                p.doi,
                p.first_author,
                p.year
        FROM evidence_units e
        JOIN papers p
          ON  e.source_review_doi = p.doi
          OR  e.primary_paper_doi  = p.doi
        WHERE p.topic = 'co2a'
        """,
        conn,
    )
    conn.close()
    return df


# ── Normalise labels ──────────────────────────────────────────────────────────

METAL_ALIASES = {
    "Zn, Cr": "ZnCr", "Cu, Zn": "CuZn", "Pd, Zn": "PdZn",
    "Co, Ir": "CoIr", "In, Zr": "InZr",
}

def norm_metal(m: str | None) -> str:
    if not m:
        return "Unknown"
    m = m.strip()
    return METAL_ALIASES.get(m, m)

SUPPORT_MAP = {
    "ZrO₂": "ZrO2", "SiO₂": "SiO2", "Al₂O₃": "Al2O3",
    "CeO₂": "CeO2", "TiO₂": "TiO2", "ZnO₂": "ZnO",
    "ZnO-ZrO₂": "ZnO-ZrO2",
}

def norm_support(s: str | None) -> str:
    if not s:
        return "Unknown"
    s = s.strip()
    return SUPPORT_MAP.get(s, s)

ZEOLITE_MAP = {
    "MFI": "ZSM-5", "H-ZSM-5": "ZSM-5", "HZSM-5": "ZSM-5",
}

def norm_zeolite(z: str | None) -> str:
    if not z:
        return "Unknown"
    z = z.strip()
    return ZEOLITE_MAP.get(z, z)


# ── Helper: draw heatmap ──────────────────────────────────────────────────────

def draw_heatmap(pivot_val: pd.DataFrame, pivot_n: pd.DataFrame,
                 title: str, cbar_label: str,
                 vmin: float, vmax: float,
                 cmap: str, out_path: Path) -> None:

    # Drop rows/cols that are all-NaN
    pivot_val = pivot_val.dropna(how="all").dropna(axis=1, how="all")
    pivot_n   = pivot_n.reindex(index=pivot_val.index, columns=pivot_val.columns).fillna(0)

    # Sort rows by row mean descending
    row_order = pivot_val.mean(axis=1).sort_values(ascending=False).index
    pivot_val = pivot_val.loc[row_order]
    pivot_n   = pivot_n.loc[row_order]

    nrows, ncols = pivot_val.shape
    fig, ax = plt.subplots(figsize=(max(5, ncols * 1.6), max(3, nrows * 0.65)))

    im = ax.imshow(pivot_val.values.astype(float),
                   cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")

    ax.set_xticks(range(ncols))
    ax.set_yticks(range(nrows))
    ax.set_xticklabels(pivot_val.columns, rotation=35, ha="right", fontsize=9)
    ax.set_yticklabels(pivot_val.index, fontsize=9)

    for i in range(nrows):
        for j in range(ncols):
            val = pivot_val.values[i, j]
            n   = int(pivot_n.values[i, j])
            if not np.isnan(val) and n > 0:
                color = "white" if val > (vmin + (vmax - vmin) * 0.6) else "black"
                ax.text(j, i, f"{val:.0f}%\n(n={n})",
                        ha="center", va="center", fontsize=7.5, color=color)

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.04)
    cbar.set_label(cbar_label, fontsize=9)
    ax.set_title(title, fontsize=12, pad=10)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Saved → {out_path}")
    plt.close(fig)


# ── Fig 1: active_metal × zeolite → aromatic selectivity ─────────────────────

def plot_metal_zeolite_aromatic(df: pd.DataFrame, out_dir: Path) -> None:
    sub = df[df["aromatic_sel_pct"].notna() & (df["aromatic_sel_pct"] > 0)].copy()
    sub["metal"]   = sub["active_metal"].apply(norm_metal)
    sub["zeolite"] = sub["zeolite_type"].apply(norm_zeolite)

    # Keep only rows where both metal and zeolite are known
    sub = sub[(sub["metal"] != "Unknown") & (sub["zeolite"] != "Unknown")]

    pv_mean = sub.groupby(["metal", "zeolite"])["aromatic_sel_pct"].mean().unstack()
    pv_n    = sub.groupby(["metal", "zeolite"])["aromatic_sel_pct"].count().unstack()

    draw_heatmap(
        pv_mean, pv_n,
        title="CO₂→Aromatics: Aromatic Selectivity\nActive Metal × Zeolite Type",
        cbar_label="Mean Aromatic Selectivity (%)",
        vmin=0, vmax=80, cmap="YlOrRd",
        out_path=out_dir / "co2_heatmap_metal_zeolite_aromatic.png",
    )


# ── Fig 2: active_metal × support → CO2 conversion ───────────────────────────

def plot_metal_support_conv(df: pd.DataFrame, out_dir: Path) -> None:
    sub = df[df["co2_conv_pct"].notna() & (df["co2_conv_pct"] > 0)
             & (df["co2_conv_pct"] <= 100)].copy()
    sub["metal"]   = sub["active_metal"].apply(norm_metal)
    sub["support_n"] = sub["support"].apply(norm_support)

    sub = sub[(sub["metal"] != "Unknown") & (sub["support_n"] != "Unknown")]

    # Keep only supports with >= 3 data points total
    support_counts = sub["support_n"].value_counts()
    valid_supports = support_counts[support_counts >= 3].index
    sub = sub[sub["support_n"].isin(valid_supports)]

    # Keep only metals with >= 3 data points
    metal_counts = sub["metal"].value_counts()
    valid_metals = metal_counts[metal_counts >= 3].index
    sub = sub[sub["metal"].isin(valid_metals)]

    pv_mean = sub.groupby(["metal", "support_n"])["co2_conv_pct"].mean().unstack()
    pv_n    = sub.groupby(["metal", "support_n"])["co2_conv_pct"].count().unstack()

    draw_heatmap(
        pv_mean, pv_n,
        title="CO₂ Hydrogenation: CO₂ Conversion\nActive Metal × Support Material",
        cbar_label="Mean CO₂ Conversion (%)",
        vmin=0, vmax=60, cmap="Blues",
        out_path=out_dir / "co2_heatmap_metal_support_conversion.png",
    )


# ── Fig 3: Scatter — temperature × aromatic selectivity by catalyst group ─────

METAL_PALETTE = {
    "Cu":  "#1f77b4", "Fe":  "#d62728", "In":  "#ff7f0e",
    "Zn":  "#2ca02c", "Pd":  "#9467bd", "Co":  "#8c564b",
    "Rh":  "#e377c2", "Ni":  "#7f7f7f", "Pt":  "#bcbd22",
    "ZnCr":"#17becf",  "CuZn":"#aec7e8", "PdZn":"#ffbb78",
    "Unknown": "#cccccc",
}

def plot_temp_aromatic_scatter(df: pd.DataFrame, out_dir: Path) -> None:
    sub = df[
        df["aromatic_sel_pct"].notna() & (df["aromatic_sel_pct"] > 0) &
        df["temperature_c"].notna()    & (df["temperature_c"] > 0)
    ].copy()
    sub["metal"] = sub["active_metal"].apply(norm_metal)

    # Collapse rare metals to "Other"
    top_metals = sub["metal"].value_counts().head(8).index
    sub["metal_plot"] = sub["metal"].apply(lambda m: m if m in top_metals else "Other")

    fig, ax = plt.subplots(figsize=(9, 6))
    for metal, grp in sub.groupby("metal_plot"):
        color = METAL_PALETTE.get(metal, "#999999")
        ax.scatter(grp["temperature_c"], grp["aromatic_sel_pct"],
                   label=metal, color=color, s=65, alpha=0.8,
                   edgecolors="white", linewidths=0.5)

    ax.set_xlabel("Reaction Temperature (°C)", fontsize=12)
    ax.set_ylabel("Total Aromatic Selectivity (%)", fontsize=12)
    ax.set_title("CO₂→Aromatics: Temperature vs Aromatic Selectivity\nby Active Metal",
                 fontsize=13)
    ax.axhline(50, color="grey", lw=0.8, ls="--", alpha=0.5)
    ax.set_xlim(50, 600)
    ax.set_ylim(-2, 105)
    ax.legend(title="Active Metal", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = out_dir / "co2_scatter_temp_vs_aromatic.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.close(fig)


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame) -> None:
    df2 = df.copy()
    df2["metal"] = df2["active_metal"].apply(norm_metal)
    tbl = (
        df2[df2["metal"] != "Unknown"]
        .groupby("metal")
        .agg(
            n             = ("aromatic_sel_pct", "count"),
            aromatic_mean = ("aromatic_sel_pct", "mean"),
            aromatic_max  = ("aromatic_sel_pct", "max"),
            co2_conv_mean = ("co2_conv_pct",     "mean"),
        )
        .sort_values("aromatic_mean", ascending=False)
    )
    print("\nCO₂→Aromatics summary by active metal:")
    print(tbl.to_string(float_format="{:.1f}".format))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "figures"))
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_co2_data()
    print(f"Loaded {len(df)} CO₂ units total.")
    print_summary(df)

    plot_metal_zeolite_aromatic(df, out_dir)
    plot_metal_support_conv(df, out_dir)
    plot_temp_aromatic_scatter(df, out_dir)


if __name__ == "__main__":
    main()

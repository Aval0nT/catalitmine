"""
CO2 Conversion Focused Visualization (363 data points)

Fig 1 — Stripplot: CO2 conversion distribution per active metal (all 363 pts)
Fig 2 — Heatmap:  active_metal × support → mean CO2 conversion
Fig 3 — Histogram: overall CO2 conversion distribution with metal breakdown

Usage:
  python3 scripts/analysis/visualize_co2_conversion.py
"""

from __future__ import annotations
import argparse, sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB   = ROOT / "db" / "catalysis.db"

SUPPORT_ALIASES = {
    "ZrO₂": "ZrO2", "SiO₂": "SiO2", "Al₂O₃": "Al2O3", "CeO₂": "CeO2",
    "TiO₂": "TiO2", "ZnO-ZrO₂": "ZnO-ZrO2", "α-Al2O3": "Al2O3",
    "H-ZSM-5": "HZSM-5", "ZnZSM-5": "HZSM-5",
}
METAL_ALIASES = {
    "Zn, Cr": "ZnCr", "Cu, Zn": "CuZn", "Cu, Fe": "CuFe",
    "Cu, Zn, Zr": "CuZnZr",
}
METAL_PALETTE = {
    "Cu":     "#1f77b4",
    "Fe":     "#d62728",
    "In":     "#ff7f0e",
    "Zn":     "#2ca02c",
    "Pd":     "#9467bd",
    "Co":     "#8c564b",
    "Rh":     "#e377c2",
    "ZnCr":   "#17becf",
    "CuZnZr": "#bcbd22",
    "Other":  "#aaaaaa",
    "Unknown":"#cccccc",
}

def load() -> pd.DataFrame:
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query("""
        SELECT e.active_metal, e.support, e.zeolite_type, e.catalyst_system,
               e.methanol_conv_pct AS co2_conv,
               e.temperature_c, e.pressure_mpa,
               p.first_author, p.year, p.doi
        FROM evidence_units e
        JOIN papers p ON e.source_review_doi=p.doi OR e.primary_paper_doi=p.doi
        WHERE p.topic='co2a'
          AND e.methanol_conv_pct > 0
          AND e.methanol_conv_pct <= 100
    """, conn)
    conn.close()
    return df

def norm_metal(m):
    if not m: return "Unknown"
    m = m.strip()
    return METAL_ALIASES.get(m, m)

def norm_support(s):
    if not s: return "Unknown"
    s = s.strip()
    return SUPPORT_ALIASES.get(s, s)

def metal_color(m):
    return METAL_PALETTE.get(m, METAL_PALETTE["Other"])


# ── Fig 1: Stripplot — CO2 conv per metal ────────────────────────────────────

def plot_strip(df: pd.DataFrame, out_dir: Path) -> None:
    df = df.copy()
    df["metal"] = df["active_metal"].apply(norm_metal)

    # Order by median conversion
    order = (df.groupby("metal")["co2_conv"]
               .median()
               .sort_values(ascending=False)
               .index.tolist())

    fig, ax = plt.subplots(figsize=(11, 6))
    rng = np.random.default_rng(42)

    for i, metal in enumerate(order):
        sub = df[df["metal"] == metal]["co2_conv"].dropna()
        jitter = rng.uniform(-0.3, 0.3, len(sub))
        color = metal_color(metal)
        ax.scatter(sub, i + jitter, color=color, alpha=0.65, s=40,
                   edgecolors="white", linewidths=0.3)
        # median bar
        ax.plot([sub.median()], [i], marker="|", markersize=20,
                color="black", markeredgewidth=2.5)
        # annotate n
        ax.text(101, i, f"n={len(sub)}", va="center", fontsize=8, color="#555")

    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order, fontsize=10)
    ax.set_xlabel("CO₂ Conversion (%)", fontsize=12)
    ax.set_title("CO₂ Hydrogenation: Conversion Distribution by Active Metal\n"
                 "(|) = median,  n = data points", fontsize=13)
    ax.set_xlim(-2, 108)
    ax.axvline(20, color="grey", lw=0.8, ls="--", alpha=0.5)
    ax.axvline(50, color="grey", lw=0.8, ls="--", alpha=0.5)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    out = out_dir / "co2_strip_conv_by_metal.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.close(fig)


# ── Fig 2: Heatmap — metal × support ────────────────────────────────────────

def plot_heatmap(df: pd.DataFrame, out_dir: Path) -> None:
    df = df.copy()
    df["metal"]   = df["active_metal"].apply(norm_metal)
    df["support_n"] = df["support"].apply(norm_support)

    sub = df[(df["metal"] != "Unknown") & (df["support_n"] != "Unknown")]

    # Keep metal/support combos with >= 2 data points
    grp = sub.groupby(["metal", "support_n"])["co2_conv"]
    pv_mean = grp.mean().unstack(fill_value=np.nan)
    pv_n    = grp.count().unstack(fill_value=0)

    # Filter: at least 3 rows in support column total, at least 2 for metal row
    col_totals = pv_n.sum(axis=0)
    row_totals = pv_n.sum(axis=1)
    pv_mean = pv_mean.loc[row_totals >= 3, col_totals >= 3]
    pv_n    = pv_n.loc[pv_mean.index, pv_mean.columns]

    # Sort rows by mean conversion
    row_order = pv_mean.mean(axis=1).sort_values(ascending=False).index
    pv_mean = pv_mean.loc[row_order]
    pv_n    = pv_n.loc[row_order]

    nrows, ncols = pv_mean.shape
    fig, ax = plt.subplots(figsize=(max(7, ncols * 1.3), max(4, nrows * 0.75)))

    im = ax.imshow(pv_mean.values.astype(float),
                   cmap="Blues", vmin=0, vmax=55, aspect="auto")

    ax.set_xticks(range(ncols))
    ax.set_yticks(range(nrows))
    ax.set_xticklabels(pv_mean.columns, rotation=35, ha="right", fontsize=9)
    ax.set_yticklabels(pv_mean.index, fontsize=9)

    for i in range(nrows):
        for j in range(ncols):
            val = pv_mean.values[i, j]
            n   = int(pv_n.values[i, j])
            if not np.isnan(val) and n > 0:
                color = "white" if val > 35 else "black"
                ax.text(j, i, f"{val:.0f}%\n(n={n})",
                        ha="center", va="center", fontsize=8, color=color)

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.04)
    cbar.set_label("Mean CO₂ Conversion (%)", fontsize=10)
    ax.set_title("CO₂ Hydrogenation: CO₂ Conversion\nActive Metal × Support Material",
                 fontsize=13, pad=10)
    fig.tight_layout()
    out = out_dir / "co2_heatmap_metal_support_conv.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.close(fig)


# ── Fig 3: Histogram — overall distribution, stacked by metal ────────────────

def plot_histogram(df: pd.DataFrame, out_dir: Path) -> None:
    df = df.copy()
    df["metal"] = df["active_metal"].apply(norm_metal)

    # Collapse minor metals
    top = df["metal"].value_counts().head(6).index.tolist()
    df["metal_plot"] = df["metal"].apply(
        lambda m: m if m in top else ("Unknown" if m == "Unknown" else "Other")
    )

    bins = np.arange(0, 105, 5)
    fig, ax = plt.subplots(figsize=(11, 5))

    metals_order = [m for m in top if m != "Unknown"] + ["Other", "Unknown"]
    metals_present = [m for m in metals_order if m in df["metal_plot"].unique()]

    data_by_metal = [df[df["metal_plot"] == m]["co2_conv"].dropna().values
                     for m in metals_present]
    colors = [metal_color(m) for m in metals_present]

    ax.hist(data_by_metal, bins=bins, stacked=True, color=colors,
            label=metals_present, alpha=0.85, edgecolor="white", linewidth=0.4)

    ax.set_xlabel("CO₂ Conversion (%)", fontsize=12)
    ax.set_ylabel("Number of data points", fontsize=12)
    ax.set_title(f"CO₂ Hydrogenation: Overall Conversion Distribution\n"
                 f"(n = {len(df)} data points from literature)", fontsize=13)
    ax.axvline(df["co2_conv"].median(), color="black", lw=1.5, ls="--",
               label=f"median = {df['co2_conv'].median():.0f}%")
    ax.legend(title="Active Metal", fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    out = out_dir / "co2_histogram_conversion.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.close(fig)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "figures"))
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load()
    print(f"Loaded {len(df)} CO₂ conversion data points.")

    plot_strip(df, out_dir)
    plot_heatmap(df, out_dir)
    plot_histogram(df, out_dir)

if __name__ == "__main__":
    main()

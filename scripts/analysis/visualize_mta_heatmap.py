"""
MTA Catalyst Visualization
===========================
Generates exploratory plots for MTA/MTH aromatic selectivity data:

  Fig 1 — Scatter: methanol conversion vs aromatic selectivity, coloured by catalyst group
  Fig 2 — Heatmap: catalyst group × zeolite type → mean aromatic selectivity
  Fig 3 — Stripplot: aromatic selectivity distribution per catalyst group

Usage:
  python3 scripts/analysis/visualize_mta_heatmap.py [--out figures/]
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB   = ROOT / "db" / "catalysis.db"


# ── 1. Load data ─────────────────────────────────────────────────────────────

def load_mta_data() -> pd.DataFrame:
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query(
        """
        SELECT  e.active_metal,
                e.promoter,
                e.zeolite_type,
                e.support,
                e.catalyst_system,
                e.si_al_ratio,
                e.metal_loading_wt,
                e.methanol_conv_pct,
                e.aromatic_sel_pct,
                e.btx_sel_pct,
                e.temperature_c,
                e.tos_h,
                p.doi,
                p.first_author,
                p.year
        FROM evidence_units e
        JOIN papers p
          ON  e.source_review_doi = p.doi
          OR  e.primary_paper_doi  = p.doi
        WHERE p.topic = 'mta'
          AND e.aromatic_sel_pct IS NOT NULL
          AND e.aromatic_sel_pct > 0
          AND e.aromatic_sel_pct <= 100
        """,
        conn,
    )
    conn.close()
    return df


# ── 2. Classify catalyst into a readable group ────────────────────────────────

def classify_catalyst(row) -> str:
    metal    = (row["active_metal"] or "").strip().upper()
    promoter = (row["promoter"]     or "").strip().upper()
    system   = (row["catalyst_system"] or "").lower()

    if "ga" in system:
        return "Ga/ZSM-5"
    if metal == "ZN" and promoter == "P":
        return "Zn+P/ZSM-5"
    if metal == "ZN":
        return "Zn/ZSM-5"
    if "ga" in metal.lower():
        return "Ga/ZSM-5"
    if "mo" in metal.lower():
        return "Mo/ZSM-5"
    if "fe" in metal.lower():
        return "Fe/ZSM-5"
    if "cu" in metal.lower():
        return "Cu/ZSM-5"
    if "ssz" in system or "ssz-24" in system:
        return "SSZ-24 (bare)"
    if "sapo" in system:
        return "SAPO"
    # H-form / unmodified zeolite
    if metal == "" and promoter == "":
        zeo = (row["zeolite_type"] or row["support"] or "").upper()
        if "ZSM" in zeo:
            return "H-ZSM-5"
        if "SAPO" in zeo:
            return "SAPO"
        return "H-form zeolite"
    return f"{metal}/zeolite" if metal else "Other"


# ── 3. Palette ────────────────────────────────────────────────────────────────

PALETTE = {
    "Zn/ZSM-5":      "#1f77b4",
    "Zn+P/ZSM-5":    "#aec7e8",
    "Ga/ZSM-5":      "#ff7f0e",
    "Mo/ZSM-5":      "#2ca02c",
    "Fe/ZSM-5":      "#d62728",
    "Cu/ZSM-5":      "#9467bd",
    "H-ZSM-5":       "#8c564b",
    "H-form zeolite":"#e377c2",
    "SSZ-24 (bare)": "#7f7f7f",
    "SAPO":          "#bcbd22",
    "Other":         "#17becf",
}


# ── 4. Fig 1: Scatter — conversion vs aromatic selectivity ───────────────────

def plot_scatter(df: pd.DataFrame, out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))

    for grp, sub in df.groupby("cat_group"):
        mask = sub["methanol_conv_pct"].notna()
        color = PALETTE.get(grp, "#333333")
        # points WITH conversion data
        ax.scatter(
            sub.loc[mask, "methanol_conv_pct"],
            sub.loc[mask, "aromatic_sel_pct"],
            label=grp, color=color, s=70, alpha=0.8, edgecolors="white", linewidths=0.5,
        )

    ax.set_xlabel("Methanol Conversion (%)", fontsize=12)
    ax.set_ylabel("Total Aromatic Selectivity (%)", fontsize=12)
    ax.set_title("MTA: Methanol Conversion vs Aromatic Selectivity\nby Catalyst Type", fontsize=13)
    ax.set_xlim(-2, 105)
    ax.set_ylim(-2, 105)
    ax.axhline(50, color="grey", lw=0.8, ls="--", alpha=0.5)
    ax.axvline(90, color="grey", lw=0.8, ls="--", alpha=0.5)
    ax.legend(title="Catalyst group", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    out = out_dir / "mta_scatter_conv_vs_aromatic.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.close(fig)


# ── 5. Fig 2: Heatmap — cat_group × zeolite → mean aromatic sel ──────────────

def plot_heatmap(df: pd.DataFrame, out_dir: Path) -> None:
    # Normalise zeolite label
    def norm_zeo(row):
        zeo = (row["zeolite_type"] or row["support"] or "").upper()
        if "ZSM-5" in zeo or "ZSM5" in zeo:
            return "ZSM-5"
        if "SAPO" in zeo:
            return "SAPO"
        if "SSZ" in zeo:
            return "SSZ-24"
        return "Unknown"

    df = df.copy()
    df["zeolite_norm"] = df.apply(norm_zeo, axis=1)

    pivot_mean = (
        df.groupby(["cat_group", "zeolite_norm"])["aromatic_sel_pct"]
        .mean()
        .unstack(fill_value=np.nan)
    )
    pivot_n = (
        df.groupby(["cat_group", "zeolite_norm"])["aromatic_sel_pct"]
        .count()
        .unstack(fill_value=0)
    )

    # Sort by overall mean
    pivot_mean = pivot_mean.loc[
        pivot_mean.mean(axis=1).sort_values(ascending=False).index
    ]
    pivot_n = pivot_n.reindex(index=pivot_mean.index, columns=pivot_mean.columns)

    fig, ax = plt.subplots(figsize=(max(6, pivot_mean.shape[1] * 1.8),
                                    max(4, pivot_mean.shape[0] * 0.7)))
    im = ax.imshow(pivot_mean.values, cmap="YlOrRd", vmin=0, vmax=100, aspect="auto")

    ax.set_xticks(range(pivot_mean.shape[1]))
    ax.set_yticks(range(pivot_mean.shape[0]))
    ax.set_xticklabels(pivot_mean.columns, rotation=30, ha="right", fontsize=10)
    ax.set_yticklabels(pivot_mean.index, fontsize=10)

    # Annotate each cell
    for i in range(pivot_mean.shape[0]):
        for j in range(pivot_mean.shape[1]):
            val = pivot_mean.values[i, j]
            n   = pivot_n.values[i, j]
            if not np.isnan(val) and n > 0:
                txt = f"{val:.0f}%\n(n={n})"
                color = "white" if val > 60 else "black"
                ax.text(j, i, txt, ha="center", va="center", fontsize=8, color=color)

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.04)
    cbar.set_label("Mean Aromatic Selectivity (%)", fontsize=10)
    ax.set_title("MTA Aromatic Selectivity Heatmap\nCatalyst Group × Zeolite Type", fontsize=13)
    fig.tight_layout()

    out = out_dir / "mta_heatmap_catalyst_zeolite.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.close(fig)


# ── 6. Fig 3: Stripplot — selectivity distribution per group ─────────────────

def plot_strip(df: pd.DataFrame, out_dir: Path) -> None:
    order = (
        df.groupby("cat_group")["aromatic_sel_pct"]
        .median()
        .sort_values(ascending=False)
        .index.tolist()
    )

    fig, ax = plt.subplots(figsize=(10, 5))
    y_pos = {g: i for i, g in enumerate(order)}

    for grp in order:
        sub = df[df["cat_group"] == grp]["aromatic_sel_pct"].dropna()
        y   = y_pos[grp]
        jitter = np.random.default_rng(42).uniform(-0.25, 0.25, len(sub))
        ax.scatter(sub, y + jitter,
                   color=PALETTE.get(grp, "#333"), alpha=0.7, s=50,
                   edgecolors="white", linewidths=0.4)
        # median line
        ax.plot([sub.median()], [y], marker="|", markersize=18,
                color="black", markeredgewidth=2.5)

    ax.set_yticks(list(y_pos.values()))
    ax.set_yticklabels(list(y_pos.keys()), fontsize=10)
    ax.set_xlabel("Total Aromatic Selectivity (%)", fontsize=12)
    ax.set_title("MTA Aromatic Selectivity by Catalyst Group\n(|) = median", fontsize=13)
    ax.set_xlim(-2, 105)
    ax.axvline(50, color="grey", lw=0.8, ls="--", alpha=0.5)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()

    out = out_dir / "mta_strip_aromatic_by_catalyst.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.close(fig)


# ── 7. Print summary table ────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame) -> None:
    tbl = (
        df.groupby("cat_group")
        .agg(
            n            = ("aromatic_sel_pct", "count"),
            aromatic_mean= ("aromatic_sel_pct", "mean"),
            aromatic_max = ("aromatic_sel_pct", "max"),
            conv_mean    = ("methanol_conv_pct", "mean"),
        )
        .sort_values("aromatic_mean", ascending=False)
    )
    print("\nSummary table:")
    print(tbl.to_string(float_format="{:.1f}".format))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "figures"), help="Output directory")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_mta_data()
    print(f"Loaded {len(df)} MTA rows with aromatic selectivity data.")

    df["cat_group"] = df.apply(classify_catalyst, axis=1)
    print_summary(df)

    plot_scatter(df, out_dir)
    plot_heatmap(df, out_dir)
    plot_strip(df, out_dir)


if __name__ == "__main__":
    main()

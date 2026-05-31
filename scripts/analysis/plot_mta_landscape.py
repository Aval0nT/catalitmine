"""
MTA Catalyst Landscape — heatmap + scatter for supervisor meeting.

Output: outputs/figures/mta_landscape.pdf  (and .png)

Figures:
  1. Heatmap: Active metal × Temperature bin → median aromatic selectivity
  2. Scatter: Temperature vs Aromatic selectivity, coloured by active metal,
              sized by year (recent = larger), labelled with first author
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

ROOT    = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "db" / "catalysis.db"
OUT_DIR = ROOT / "outputs" / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

conn = sqlite3.connect(DB_PATH)

df = pd.read_sql_query("""
    SELECT
        p.year, p.first_author, p.journal,
        e.catalyst_system, e.active_metal, e.zeolite_type,
        e.temperature_c, e.pressure_mpa, e.whsv,
        e.aromatic_sel_pct, e.btx_sel_pct, e.methanol_conv_pct,
        e.tos_h, e.preparation_method
    FROM evidence_units e
    JOIN papers p ON e.source_review_doi = p.doi
    WHERE p.paper_type = 'primary'
      AND p.topic = 'mta'
      AND e.aromatic_sel_pct IS NOT NULL
      AND e.temperature_c IS NOT NULL
    ORDER BY p.year
""", conn)
conn.close()

# Clean metal labels
def norm_metal(m):
    if pd.isna(m) or str(m).strip().lower() in ("", "none", "null"):
        return "None (parent)"
    return str(m).strip()

df["metal"] = df["active_metal"].apply(norm_metal)

# Temperature bins
bins  = [300, 375, 410, 440, 475, 600]
labels = ["300–375", "375–410", "410–440", "440–475", ">475"]
df["T_bin"] = pd.cut(df["temperature_c"], bins=bins, labels=labels)

# Metal order by count
metal_order = df["metal"].value_counts().index.tolist()

# Color palette
palette = {
    "Zn":             "#E63946",
    "Ga":             "#2196F3",
    "Ni":             "#4CAF50",
    "Mo":             "#FF9800",
    "Fe":             "#9C27B0",
    "In":             "#00BCD4",
    "None (parent)":  "#78909C",
}
def metal_color(m):
    return palette.get(m, "#BDBDBD")

# ---------------------------------------------------------------------------
# Figure 1 — Heatmap: metal × T_bin → median aromatic selectivity
# ---------------------------------------------------------------------------

pivot = (
    df.groupby(["metal", "T_bin"], observed=True)["aromatic_sel_pct"]
    .agg(["median", "count"])
    .reset_index()
)
pivot_med = pivot.pivot(index="metal", columns="T_bin", values="median").reindex(metal_order)
pivot_cnt = pivot.pivot(index="metal", columns="T_bin", values="count").reindex(metal_order)
pivot_med = pivot_med.reindex(columns=labels)
pivot_cnt = pivot_cnt.reindex(columns=labels)

fig1, ax1 = plt.subplots(figsize=(9, 4))
im = ax1.imshow(
    pivot_med.values.astype(float),
    cmap="YlOrRd", aspect="auto",
    vmin=0, vmax=80,
    interpolation="nearest",
)
ax1.set_xticks(range(len(labels)))
ax1.set_xticklabels(labels, fontsize=10)
ax1.set_yticks(range(len(metal_order)))
ax1.set_yticklabels(metal_order, fontsize=10)
ax1.set_xlabel("Temperature (°C)", fontsize=11)
ax1.set_ylabel("Active Metal", fontsize=11)
ax1.set_title("MTA Primary Literature — Aromatic Selectivity Landscape\n"
              "(median %, cell numbers = data points)", fontsize=12, pad=10)

# Annotate cells
for i, metal in enumerate(metal_order):
    for j, tbin in enumerate(labels):
        val = pivot_med.values[i, j]
        cnt = pivot_cnt.values[i, j]
        if not np.isnan(val):
            ax1.text(j, i, f"{val:.0f}%\n(n={int(cnt)})",
                     ha="center", va="center", fontsize=8,
                     color="white" if val > 45 else "black")

cbar = fig1.colorbar(im, ax=ax1, shrink=0.8, label="Aromatic Selectivity (%)")
fig1.tight_layout()
fig1.savefig(OUT_DIR / "mta_heatmap.png", dpi=150, bbox_inches="tight")
fig1.savefig(OUT_DIR / "mta_heatmap.pdf", bbox_inches="tight")
print(f"Saved: mta_heatmap.png / .pdf")

# ---------------------------------------------------------------------------
# Figure 2 — Scatter: T vs arom%, coloured by metal, labelled
# ---------------------------------------------------------------------------

fig2, ax2 = plt.subplots(figsize=(11, 7))

# Year → marker size
year_min, year_max = df["year"].min(), df["year"].max()

for _, row in df.iterrows():
    c   = metal_color(row["metal"])
    sz  = 60 + 200 * (row["year"] - year_min) / max(year_max - year_min, 1)
    ax2.scatter(row["temperature_c"], row["aromatic_sel_pct"],
                color=c, s=sz, alpha=0.75, edgecolors="white", linewidths=0.5, zorder=3)

# Label clusters: show author+year for high-selectivity or notable points
labeled = set()
for _, row in df.sort_values("aromatic_sel_pct", ascending=False).iterrows():
    key = (round(row["temperature_c"] / 10) * 10, round(row["aromatic_sel_pct"] / 5) * 5)
    if key not in labeled:
        labeled.add(key)
        ax2.annotate(
            f"{row['first_author']} {row['year']}",
            (row["temperature_c"], row["aromatic_sel_pct"]),
            fontsize=6.5, alpha=0.8,
            xytext=(4, 3), textcoords="offset points",
        )

ax2.set_xlabel("Temperature (°C)", fontsize=12)
ax2.set_ylabel("Aromatic Selectivity (%)", fontsize=12)
ax2.set_title("MTA Primary Literature: Temperature vs Aromatic Selectivity\n"
              "(marker size ∝ publication year; colour = active metal)", fontsize=12)
ax2.grid(True, alpha=0.3, linestyle="--")
ax2.set_xlim(df["temperature_c"].min() - 20, df["temperature_c"].max() + 20)
ax2.set_ylim(-2, 105)

# Legend
legend_handles = [
    mpatches.Patch(color=metal_color(m), label=m)
    for m in metal_order
]
# Year size legend
for yr, label in [(year_min, str(year_min)), (year_max, str(year_max))]:
    sz = 60 + 200 * (yr - year_min) / max(year_max - year_min, 1)
    legend_handles.append(
        plt.scatter([], [], s=sz, color="gray", alpha=0.6, label=f"Year {label}")
    )
ax2.legend(handles=legend_handles, loc="upper left", fontsize=8,
           framealpha=0.9, ncol=2)

fig2.tight_layout()
fig2.savefig(OUT_DIR / "mta_scatter.png", dpi=150, bbox_inches="tight")
fig2.savefig(OUT_DIR / "mta_scatter.pdf", bbox_inches="tight")
print(f"Saved: mta_scatter.png / .pdf")

# ---------------------------------------------------------------------------
# Figure 3 — Bar: best selectivity per metal (for presentation summary)
# ---------------------------------------------------------------------------

summary = (
    df.groupby("metal")["aromatic_sel_pct"]
    .agg(["max", "median", "count"])
    .reset_index()
    .sort_values("max", ascending=True)
)

fig3, ax3 = plt.subplots(figsize=(8, 4))
colors = [metal_color(m) for m in summary["metal"]]
bars = ax3.barh(summary["metal"], summary["max"], color=colors,
                alpha=0.85, edgecolor="white", height=0.55, label="Max")
ax3.barh(summary["metal"], summary["median"], color=colors,
         alpha=0.4, edgecolor="none", height=0.55, label="Median")

for bar, (_, row) in zip(bars, summary.iterrows()):
    ax3.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
             f"  max {row['max']:.0f}%  (n={int(row['count'])})",
             va="center", fontsize=9)

ax3.set_xlabel("Aromatic Selectivity (%)", fontsize=11)
ax3.set_title("Best Reported Aromatic Selectivity by Active Metal\n"
              "(solid = max, faded = median)", fontsize=11)
ax3.set_xlim(0, 105)
ax3.grid(axis="x", alpha=0.3, linestyle="--")
ax3.legend(fontsize=9, loc="lower right")
fig3.tight_layout()
fig3.savefig(OUT_DIR / "mta_by_metal.png", dpi=150, bbox_inches="tight")
fig3.savefig(OUT_DIR / "mta_by_metal.pdf", bbox_inches="tight")
print(f"Saved: mta_by_metal.png / .pdf")

print(f"\nAll figures saved to {OUT_DIR}")
print(f"\nData summary ({len(df)} points):")
print(df.groupby("metal")[["temperature_c","aromatic_sel_pct"]].describe().round(1).to_string())

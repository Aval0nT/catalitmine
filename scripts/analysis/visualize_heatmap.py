"""
CO2 hydrogenation catalyst heatmap:
  Fig 6 — Scatter: CO2 conversion vs selectivity, colored by active metal
  Fig 7 — Dual heatmap: metal x support → mean selectivity / mean conversion
"""
import sqlite3
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

VIZ_DIR = Path(__file__).resolve().parents[2] / "outputs" / "viz"
VIZ_DIR.mkdir(parents=True, exist_ok=True)
DB = Path(__file__).resolve().parents[2] / "db" / "catalysis.db"

conn = sqlite3.connect(DB)
rows = conn.execute("""
    SELECT active_metal, support, zeolite_type,
           methanol_conv_pct, btx_sel_pct, catalyst_system
    FROM evidence_units
    WHERE source_review_doi = '10.1016/j.chempr.2021.02.024'
      AND methanol_conv_pct IS NOT NULL AND btx_sel_pct IS NOT NULL
      AND active_metal IS NOT NULL
""").fetchall()


def norm_metal(m):
    if not m:
        return "Other"
    m = m.strip()
    if "," in m:
        m = m.split(",")[0].strip()
    return m


def norm_support(sup, zeo):
    for s in [sup, zeo]:
        if not s:
            continue
        s = s.strip()
        if "SAPO" in s:
            return "SAPO-34"
        if "ZSM" in s:
            return "ZSM-5"
        if "ZIF" in s:
            return "ZIF-8"
        if "Al2O3" in s:
            return "Al₂O₃"
        if "carbon" in s.lower() or s == "C":
            return "C/NC"
        if "MIL" in s:
            return "MOF"
    return "No support"


data = []
for metal, sup, zeo, conv, btx, cat in rows:
    data.append({
        "metal":   norm_metal(metal),
        "support": norm_support(sup, zeo),
        "conv":    conv,
        "btx":     btx,
        "cat":     (cat or "")[:28],
    })

metals   = sorted(set(d["metal"]   for d in data))
supports = sorted(set(d["support"] for d in data))

METAL_COLORS = {
    "Fe": "#E05C5C",
    "In": "#4C9BE8",
    "Cu": "#F0A030",
    "Zn": "#5CB85C",
    "Zr": "#9B5CE8",
}

# ── Figure 6: Scatter ────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 6))
for metal in metals:
    pts = [d for d in data if d["metal"] == metal]
    xs = [p["conv"] for p in pts]
    ys = [p["btx"]  for p in pts]
    c  = METAL_COLORS.get(metal, "#aaa")
    ax.scatter(xs, ys, c=c, s=85, alpha=0.85, label=metal,
               zorder=3, edgecolors="white", linewidth=0.5)

for d in data:
    if d["btx"] >= 78 or d["conv"] >= 50:
        ax.annotate(d["cat"], (d["conv"], d["btx"]),
                    fontsize=7, ha="left", va="bottom",
                    xytext=(4, 3), textcoords="offset points", color="#444")

ax.set_xlabel("CO₂ Conversion (%)", fontsize=11)
ax.set_ylabel("Olefin / BTX Selectivity (%)", fontsize=11)
ax.set_title(
    "CO₂ Hydrogenation — Conversion vs Selectivity\n(ChemPR 2021, n=34)",
    fontweight="bold", fontsize=12)
ax.legend(title="Active Metal", fontsize=9, title_fontsize=9)
ax.grid(True, alpha=0.25)
ax.set_xlim(-1, 75)
ax.set_ylim(-1, 100)
fig.tight_layout()
p = VIZ_DIR / "fig6_co2_scatter_metal.png"
fig.savefig(p, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  saved: {p.name}")

# ── Figure 7: Dual heatmap ───────────────────────────────────────────────────
btx_mat  = np.full((len(metals), len(supports)), np.nan)
conv_mat = np.full((len(metals), len(supports)), np.nan)
cnt_mat  = np.zeros((len(metals), len(supports)), dtype=int)

for d in data:
    i = metals.index(d["metal"])
    j = supports.index(d["support"])
    n = cnt_mat[i, j]
    if n == 0:
        btx_mat[i, j]  = d["btx"]
        conv_mat[i, j] = d["conv"]
    else:
        btx_mat[i, j]  = (btx_mat[i, j]  * n + d["btx"])  / (n + 1)
        conv_mat[i, j] = (conv_mat[i, j] * n + d["conv"]) / (n + 1)
    cnt_mat[i, j] += 1

fig, axes = plt.subplots(1, 2, figsize=(14, 4.5))

for ax, mat, title, cmap in [
    (axes[0], btx_mat,  "Mean Olefin/BTX Selectivity (%)", "YlOrRd"),
    (axes[1], conv_mat, "Mean CO₂ Conversion (%)",          "Blues"),
]:
    masked = np.ma.masked_invalid(mat)
    im = ax.imshow(masked, cmap=cmap, aspect="auto", vmin=0,
                   vmax=100 if cmap == "YlOrRd" else 70)
    ax.set_xticks(range(len(supports)))
    ax.set_xticklabels(supports, rotation=35, ha="right", fontsize=9)
    ax.set_yticks(range(len(metals)))
    ax.set_yticklabels(metals, fontsize=11)
    ax.set_title(title, fontweight="bold", fontsize=10)
    plt.colorbar(im, ax=ax, label="%", shrink=0.85)
    for i in range(len(metals)):
        for j in range(len(supports)):
            if not np.isnan(mat[i, j]):
                n = cnt_mat[i, j]
                txt = f"{mat[i,j]:.0f}%\n(n={n})"
                col = "white" if mat[i, j] > 60 else "black"
                ax.text(j, i, txt, ha="center", va="center",
                        fontsize=8, color=col)

fig.suptitle(
    "CO₂ Hydrogenation — Active Metal × Support\n(ChemPR 2021 review, bifunctional catalysts)",
    fontweight="bold", fontsize=12)
fig.tight_layout()
p = VIZ_DIR / "fig7_co2_heatmap_metal_support.png"
fig.savefig(p, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  saved: {p.name}")

print(f"\n{len(data)} data points | metals: {metals} | supports: {supports}")

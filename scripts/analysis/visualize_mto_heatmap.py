"""
MTO primary papers heatmap.
Pulls data from evidence_units + extra_json for olefin selectivity.
Outputs fig8 (scatter: temp vs C3 selectivity) and fig9 (heatmap: zeolite x product).
"""
import json, sqlite3, re
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from collections import defaultdict
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[2]
DB      = ROOT / "db" / "catalysis.db"
VIZ_DIR = ROOT / "outputs" / "viz"
VIZ_DIR.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(DB)

# Pull all MTA primary paper evidence with extra_json
rows = conn.execute("""
    SELECT p.first_author, p.year, e.catalyst_system, e.zeolite_type,
           e.methanol_conv_pct, e.temperature_c, e.extra_json
    FROM evidence_units e
    JOIN papers p ON e.source_review_doi = p.doi
    WHERE p.paper_type = 'primary' AND p.topic = 'mta'
      AND e.extra_json IS NOT NULL AND e.extra_json != 'null'
""").fetchall()

# Parse extra_json into structured records
records = []
for author, year, cat, zeo, conv, temp, xj in rows:
    try:
        ex = json.loads(xj)
    except Exception:
        continue
    if not ex:
        continue

    # Normalise zeolite label
    z = (zeo or cat or "").strip()
    if "SAPO-34" in z or "SAPO34" in z: z = "SAPO-34"
    elif "ZSM-5" in z or "ZSM5" in z:  z = "ZSM-5"
    elif "ZSM-22" in z:                 z = "ZSM-22"
    elif "BEA" in z or "Beta" in z:     z = "Beta"
    elif "LEV" in z:                    z = "LEV"
    elif "CHA" in z:                    z = "CHA"
    elif "AFX" in z:                    z = "AFX"
    elif "DDR" in z:                    z = "DDR"
    elif "MTT" in z or "ZSM-23" in z:  z = "ZSM-23"
    elif "MFI" in z:                    z = "ZSM-5"
    elif z == "":                       z = "Unknown"

    # Temperature (from extra_json or column)
    t = ex.get("temperature_C") or ex.get("temperature_c") or temp

    def pick(*keys):
        for k in keys:
            v = ex.get(k)
            if v is not None:
                try: return float(v)
                except: pass
        return None

    records.append({
        "author": f"{author} {year}",
        "zeolite": z,
        "conv":   conv,
        "temp":   t,
        "c2":     pick("c2_pct", "ethylene_pct", "ethene_pct",
                       "ethylene_selectivity_pct", "ethene_selectivity_pct",
                       "ethene_selectivity_initial", "ethylene_selectivity_initial"),
        "c3":     pick("c3_pct", "propylene_pct", "propene_pct",
                       "propylene_selectivity_pct", "propene_selectivity_pct",
                       "propylene_selectivity_initial", "propene_selectivity_initial"),
        "c4":     pick("c4_olefin_pct", "c4_pct", "butene_pct", "butenes_selectivity_pct"),
        "c6plus": pick("c6plus_pct", "aromatics_pct", "aromatics_selectivity_pct",
                       "c6_plus_pct", "heavy_pct"),
        "extra":  ex,
    })

print(f"Parsed {len(records)} records with extra_json data")

# ── Fig 8: Scatter — Temperature vs C2+C3 olefin selectivity ────────────────
scatter_pts = [(r["temp"], (r["c2"] or 0) + (r["c3"] or 0), r["zeolite"], r["author"])
               for r in records if r["temp"] and (r["c2"] or r["c3"])]

ZCOLOR = {
    "ZSM-5":   "#E05C5C",
    "SAPO-34": "#4C9BE8",
    "ZSM-22":  "#F0A030",
    "Beta":    "#5CB85C",
    "LEV":     "#9B5CE8",
    "CHA":     "#5CE8E0",
    "AFX":     "#E85C9B",
    "DDR":     "#888",
    "ZSM-23":  "#aaa",
}

if scatter_pts:
    fig, ax = plt.subplots(figsize=(8, 5))
    seen = set()
    for t, sel, zeo, auth in scatter_pts:
        c = ZCOLOR.get(zeo, "#bbb")
        lbl = zeo if zeo not in seen else ""
        ax.scatter(t, sel, c=c, s=70, alpha=0.8, label=lbl, zorder=3,
                   edgecolors="white", linewidth=0.5)
        seen.add(zeo)
    ax.set_xlabel("Temperature (°C)", fontsize=11)
    ax.set_ylabel("C₂⁻ + C₃⁻ Olefin Selectivity (%)", fontsize=11)
    ax.set_title("MTO Primary Papers — Temperature vs Light Olefin Selectivity",
                 fontweight="bold", fontsize=11)
    ax.legend(title="Zeolite", fontsize=8, title_fontsize=8,
              loc="upper left", bbox_to_anchor=(1.01, 1))
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    p = VIZ_DIR / "fig8_mto_temp_vs_olefin.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved: {p.name}  ({len(scatter_pts)} pts)")
else:
    print("  [skip] fig8: no temp+selectivity pairs")

# ── Fig 9: Heatmap — zeolite type × product fraction (mean) ─────────────────
# Group by zeolite, compute mean of each product fraction
zeo_data = defaultdict(lambda: defaultdict(list))
products = ["c2", "c3", "c4", "c6plus"]
prod_labels = ["C₂⁻ (ethylene)", "C₃⁻ (propylene)", "C₄ olefins", "C₆+ / aromatics"]

for r in records:
    z = r["zeolite"]
    for p in products:
        v = r[p]
        if v is not None and 0 < v <= 100:
            zeo_data[z][p].append(v)

# Only keep zeolites with at least one product measured
zeolites = [z for z in sorted(zeo_data.keys()) if any(zeo_data[z][p] for p in products)]
mat = np.full((len(zeolites), len(products)), np.nan)
cnt = np.zeros_like(mat, dtype=int)
for i, z in enumerate(zeolites):
    for j, p in enumerate(products):
        vals = zeo_data[z][p]
        if vals:
            mat[i, j] = np.mean(vals)
            cnt[i, j] = len(vals)

if len(zeolites) >= 2:
    fig, ax = plt.subplots(figsize=(9, max(4, len(zeolites) * 0.6 + 1.5)))
    masked = np.ma.masked_invalid(mat)
    im = ax.imshow(masked, cmap="YlOrRd", aspect="auto", vmin=0, vmax=60)
    ax.set_xticks(range(len(products)))
    ax.set_xticklabels(prod_labels, fontsize=10)
    ax.set_yticks(range(len(zeolites)))
    ax.set_yticklabels(zeolites, fontsize=10)
    ax.set_title("MTO Primary Papers — Zeolite Type × Product Distribution\n(mean selectivity %)",
                 fontweight="bold", fontsize=11)
    plt.colorbar(im, ax=ax, label="Mean selectivity (%)", shrink=0.8)
    for i in range(len(zeolites)):
        for j in range(len(products)):
            if not np.isnan(mat[i, j]):
                col = "white" if mat[i, j] > 35 else "black"
                ax.text(j, i, f"{mat[i,j]:.0f}%\n(n={cnt[i,j]})",
                        ha="center", va="center", fontsize=8, color=col)
    fig.tight_layout()
    p = VIZ_DIR / "fig9_mto_zeolite_product_heatmap.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved: {p.name}  ({len(zeolites)} zeolites)")
else:
    print(f"  [skip] fig9: only {len(zeolites)} zeolite type(s) with data")

# Summary
print("\nData per zeolite:")
for z in zeolites:
    parts = {p: f"{np.mean(zeo_data[z][p]):.0f}% (n={len(zeo_data[z][p])})"
             for p in products if zeo_data[z][p]}
    print(f"  {z:<12}: {parts}")

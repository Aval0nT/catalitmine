"""
Initial visualization of current database content.
Outputs PNG files to outputs/viz/.
"""
import sqlite3, json, re
from pathlib import Path
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

ROOT    = Path(__file__).resolve().parents[2]
DB      = ROOT / "db" / "catalysis.db"
VIZ_DIR = ROOT / "outputs" / "viz"
VIZ_DIR.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(DB)

plt.rcParams.update({"figure.dpi": 150, "font.size": 10})

# ── helpers ──────────────────────────────────────────────────────────────────

def safe_float(v):
    try:
        return float(re.sub(r"[^\d.\-]", "", str(v)))
    except:
        return None

def save(fig, name):
    p = VIZ_DIR / name
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved: {p.name}")

# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 1 — MTA: zeolite type distribution
# ═══════════════════════════════════════════════════════════════════════════
MTA_DOIS = ("10.1038/s41929-018-0078-5", "10.1007/s13203-016-0156-z")

rows = conn.execute("""
    SELECT zeolite_type, COUNT(*) n FROM evidence_units
    WHERE source_review_doi IN (?,?) AND zeolite_type IS NOT NULL
    GROUP BY zeolite_type ORDER BY n DESC LIMIT 12
""", MTA_DOIS).fetchall()

fig, ax = plt.subplots(figsize=(7, 4))
labels = [r[0] for r in rows]
values = [r[1] for r in rows]
bars = ax.barh(labels[::-1], values[::-1], color="#4C9BE8")
ax.set_xlabel("Number of evidence units")
ax.set_title("MTA Reviews — Zeolite Types Mentioned", fontweight="bold")
ax.bar_label(bars, padding=3, fontsize=9)
ax.set_xlim(0, max(values) * 1.2)
fig.tight_layout()
save(fig, "fig1_mta_zeolite_types.png")

# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 2 — MTA: proposed mechanisms
# ═══════════════════════════════════════════════════════════════════════════
rows = conn.execute("""
    SELECT proposed_mechanism, COUNT(*) n FROM evidence_units
    WHERE source_review_doi IN (?,?) AND proposed_mechanism IS NOT NULL
    GROUP BY proposed_mechanism ORDER BY n DESC
""", MTA_DOIS).fetchall()

labels = [r[0].replace("_", " ") for r in rows]
values = [r[1] for r in rows]
colors = ["#E05C5C","#F0A030","#4C9BE8","#5CB85C","#9B5CE8","#5CE8E0","#E85C9B"]

fig, ax = plt.subplots(figsize=(6, 4))
wedges, texts, autotexts = ax.pie(
    values, labels=None, autopct="%1.0f%%",
    colors=colors[:len(values)], startangle=140,
    pctdistance=0.75
)
ax.legend(wedges, labels, loc="center left", bbox_to_anchor=(1, 0.5), fontsize=8)
ax.set_title("MTA Reviews — Proposed Mechanisms", fontweight="bold")
save(fig, "fig2_mta_mechanisms.png")

# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 3 — MTA: claim type × evidence type heatmap
# ═══════════════════════════════════════════════════════════════════════════
rows = conn.execute("""
    SELECT claim_type, evidence_type, COUNT(*) n FROM evidence_units
    WHERE source_review_doi IN (?,?)
      AND claim_type IS NOT NULL AND evidence_type IS NOT NULL
    GROUP BY claim_type, evidence_type
""", MTA_DOIS).fetchall()

claim_types = sorted(set(r[0] for r in rows))
evid_types  = sorted(set(r[1] for r in rows))
matrix = np.zeros((len(claim_types), len(evid_types)), dtype=int)
for ct, et, n in rows:
    matrix[claim_types.index(ct), evid_types.index(et)] = n

fig, ax = plt.subplots(figsize=(7, 4))
im = ax.imshow(matrix, cmap="Blues", aspect="auto")
ax.set_xticks(range(len(evid_types)));  ax.set_xticklabels(evid_types, rotation=30, ha="right", fontsize=8)
ax.set_yticks(range(len(claim_types))); ax.set_yticklabels(claim_types, fontsize=8)
for i in range(len(claim_types)):
    for j in range(len(evid_types)):
        if matrix[i, j] > 0:
            ax.text(j, i, str(matrix[i, j]), ha="center", va="center",
                    fontsize=9, color="white" if matrix[i, j] > 30 else "black")
ax.set_title("MTA — Claim Type × Evidence Type", fontweight="bold")
plt.colorbar(im, ax=ax, label="count")
fig.tight_layout()
save(fig, "fig3_mta_claim_evidence_heatmap.png")

# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 4 — CO₂ tables: Temperature vs CO₂ Conversion scatter
# ═══════════════════════════════════════════════════════════════════════════
table_rows = conn.execute(
    "SELECT columns_json, row_json, source_review_doi FROM table_rows"
).fetchall()

points = []   # (temp_C, co2_conv, catalyst_short, source)
for cols_j, row_j, doi in table_rows:
    cols = json.loads(cols_j)
    row  = json.loads(row_j)
    d = dict(zip(cols, row))

    # find temperature column (K or °C)
    temp = None
    for k, v in d.items():
        if re.search(r'temp|T\b', k, re.I) and re.search(r'K\b|°C|C\b', k):
            t = safe_float(v)
            if t and t > 0:
                temp = t - 273.15 if t > 400 else t  # K→°C if > 400
                break

    # find CO2 conversion column
    conv = None
    for k, v in d.items():
        if re.search(r'co.?2.*conv|x.*co.?2|conv.*co', k, re.I):
            conv = safe_float(v)
            break

    if temp and conv and -50 < temp < 600 and 0 <= conv <= 100:
        cat = str(list(d.values())[0])[:20]
        points.append((temp, conv, cat, doi))

if points:
    fig, ax = plt.subplots(figsize=(7, 5))
    color_map = {
        "10.1016/j.chempr.2021.02.024": "#4C9BE8",
        "10.1021/acs.chemrev.9b00723":  "#E05C5C",
        "10.1016/j.apcatb.2021.120073": "#5CB85C",
    }
    label_map = {"10.1016/j.chempr.2021.02.024": "ChemPR",
                 "10.1021/acs.chemrev.9b00723":  "ChemRev",
                 "10.1016/j.apcatb.2021.120073": "ApCatB"}
    plotted = {}
    for temp, conv, cat, doi in points:
        c = color_map.get(doi, "#999")
        lbl = label_map.get(doi, doi)
        sc = ax.scatter(temp, conv, color=c, alpha=0.65, s=40,
                        label=lbl if lbl not in plotted else "")
        plotted[lbl] = True

    handles = [mpatches.Patch(color=c, label=l) for l, c in
               [(v, color_map[k]) for k, v in label_map.items() if k in color_map]]
    ax.legend(handles=handles, fontsize=9)
    ax.set_xlabel("Temperature (°C)")
    ax.set_ylabel("CO₂ Conversion (%)")
    ax.set_title("CO₂ Hydrogenation — Temperature vs Conversion\n(from Vision-extracted tables)", fontweight="bold")
    ax.grid(True, alpha=0.3)
    save(fig, "fig4_co2_temp_vs_conversion.png")
    print(f"    ({len(points)} data points plotted)")
else:
    print("  [skip] fig4: no numeric points found")

# ═══════════════════════════════════════════════════════════════════════════
# FIGURE 5 — CO₂ tables: top catalysts by conversion
# ═══════════════════════════════════════════════════════════════════════════
cat_conv = defaultdict(list)
for cols_j, row_j, doi in table_rows:
    cols = json.loads(cols_j)
    row  = json.loads(row_j)
    d = dict(zip(cols, row))
    cat = str(list(d.values())[0]).strip()
    # strip ref numbers like "[50]"
    cat = re.sub(r'\s*\[\d+\]', '', cat).strip()[:35]
    conv = None
    for k, v in d.items():
        if re.search(r'co.?2.*conv|x.*co.?2|conv.*co', k, re.I):
            conv = safe_float(v)
            break
    if conv and 0 < conv <= 100 and len(cat) > 3:
        cat_conv[cat].append(conv)

# top 15 by max conversion
top = sorted(cat_conv.items(), key=lambda x: max(x[1]), reverse=True)[:15]
if top:
    fig, ax = plt.subplots(figsize=(8, 5))
    cats   = [t[0] for t in top]
    maxes  = [max(t[1]) for t in top]
    means  = [np.mean(t[1]) for t in top]
    x = np.arange(len(cats))
    ax.barh(x, maxes, color="#4C9BE8", alpha=0.7, label="Max conv.")
    ax.barh(x, means, color="#E05C5C", alpha=0.8, label="Mean conv.")
    ax.set_yticks(x); ax.set_yticklabels(cats, fontsize=7)
    ax.set_xlabel("CO₂ Conversion (%)")
    ax.set_title("Top 15 Catalysts — CO₂ Conversion\n(from Vision-extracted tables)", fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    save(fig, "fig5_co2_top_catalysts.png")

print("\nAll figures saved to outputs/viz/")

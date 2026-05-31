"""
CO2 Bifunctional Catalyst Visualization
=========================================
按化学功能分类催化剂，而不是简单按金属元素：
  - 加氢组分 (Hydrogenation): 氧化物部分，负责CO2活化
  - 芳构化组分 (Aromatization): 酸性分子筛部分，负责C-C成键

Fig 1 — Heatmap: 加氢组分 × 芳构化组分 → CO₂ 转化率
Fig 2 — Heatmap: 加氢组分 × 芳构化组分 → 芳烃选择性
Fig 3 — Stripplot: 各加氢组分的CO₂转化率分布（含"无分子筛"对照）

Usage:
  python3 scripts/analysis/visualize_co2_bifunctional.py
"""

from __future__ import annotations
import argparse, sqlite3, re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB   = ROOT / "db" / "catalysis.db"

# ── Classification logic ──────────────────────────────────────────────────────

def classify_acid_component(catalyst_system: str | None,
                             zeolite_type: str | None,
                             support: str | None) -> str:
    """Identify the aromatisation (acid/zeolite) component."""
    sources = [zeolite_type or "", catalyst_system or "", support or ""]
    combined = " ".join(sources).upper()

    if re.search(r'\bZSM-?5\b|HZSM|H-ZSM|MFI\b', combined):
        return "ZSM-5"
    if re.search(r'SAPO-?34', combined):
        return "SAPO-34"
    if re.search(r'\bSAPO\b', combined):
        return "SAPO"
    if re.search(r'\bSSZ\b|\bBETA\b|\bBEA\b', combined):
        return "Other zeolite"
    return "No zeolite"


def classify_hydro_component(catalyst_system: str | None,
                              active_metal: str | None,
                              support: str | None) -> str:
    """Identify the hydrogenation (oxide) component.

    Priority order matters — more specific patterns first.
    Multi-metal systems are labelled with the dominant oxide phase.
    """
    cs  = (catalyst_system or "").upper()
    met = (active_metal    or "").upper()
    sup = (support         or "").upper()

    # In2O3 — common CO2→MeOH oxide, often paired with ZrO2 or ZnO
    if re.search(r'IN2O3|IN₂O₃|INO[X]?(?!\w)', cs) or met.startswith("IN"):
        if re.search(r'ZNO|ZN-ZR|ZNZR|ZRO', cs):
            return "In₂O₃-ZnO/ZrO₂"
        return "In₂O₃"

    # ZnCrOx
    if re.search(r'ZN.?CR|ZNCR', cs) or re.search(r'ZN.*CR|CR.*ZN', met):
        return "ZnCrOx"

    # ZnO-ZrO2 composite (without In)
    if re.search(r'ZNO.ZRO|ZN.ZR[O]?2?|ZNZRO', cs):
        return "ZnO-ZrO₂"

    # Cu-based (most common, must come after ZnO-ZrO2 check)
    if re.search(r'\bCU\b', met) or re.search(r'^CU[^A-Z]|[^A-Z]CU[^A-Z]|CUZO|CUZN', cs):
        return "Cu"

    # Fe-based (FT route)
    if re.search(r'\bFE\b', met) or re.search(r'^FE[^A-Z]|[^A-Z]FE[^A-Z]|FE2O|FE3O', cs):
        return "Fe"

    # Pd
    if re.search(r'\bPD\b', met) or re.search(r'^PD[^A-Z]|[^A-Z]PD[^A-Z]', cs):
        return "Pd"

    # ZnO (pure or as support, without Zr)
    if re.search(r'\bZN\b', met) or re.search(r'\bZNO\b', cs + " " + sup):
        return "ZnO"

    # Noble metals
    if re.search(r'\bRH\b', met): return "Rh"
    if re.search(r'\bPT\b', met): return "Pt"
    if re.search(r'\bAU\b', met): return "Au"
    if re.search(r'\bCO\b', met): return "Co"
    if re.search(r'\bNI\b', met): return "Ni"

    return "Other/Unknown"


# ── Load & classify ───────────────────────────────────────────────────────────

def load() -> pd.DataFrame:
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query("""
        SELECT e.catalyst_system, e.active_metal, e.support, e.zeolite_type,
               e.methanol_conv_pct  AS co2_conv,
               e.aromatic_sel_pct,
               e.source_chunk_id,
               p.first_author, p.year
        FROM evidence_units e
        JOIN papers p ON e.source_review_doi=p.doi OR e.primary_paper_doi=p.doi
        WHERE p.topic='co2a'
    """, conn)
    conn.close()

    df["hydro"]   = df.apply(lambda r: classify_hydro_component(
                        r.catalyst_system, r.active_metal, r.support), axis=1)
    df["acid"]    = df.apply(lambda r: classify_acid_component(
                        r.catalyst_system, r.zeolite_type, r.support), axis=1)
    return df


# ── Heatmap helper ────────────────────────────────────────────────────────────

def draw_heatmap(pv_val: pd.DataFrame, pv_n: pd.DataFrame,
                 title: str, cbar_label: str,
                 vmin: float, vmax: float, cmap: str,
                 out_path: Path) -> None:
    pv_val = pv_val.dropna(how="all").dropna(axis=1, how="all")
    pv_n   = pv_n.reindex(index=pv_val.index, columns=pv_val.columns).fillna(0)
    order  = pv_val.mean(axis=1).sort_values(ascending=False).index
    pv_val = pv_val.loc[order]
    pv_n   = pv_n.loc[order]

    nr, nc = pv_val.shape
    fig, ax = plt.subplots(figsize=(max(5, nc * 1.8), max(3, nr * 0.75)))
    im = ax.imshow(pv_val.values.astype(float), cmap=cmap,
                   vmin=vmin, vmax=vmax, aspect="auto")
    ax.set_xticks(range(nc)); ax.set_yticks(range(nr))
    ax.set_xticklabels(pv_val.columns, rotation=30, ha="right", fontsize=9)
    ax.set_yticklabels(pv_val.index, fontsize=9)
    for i in range(nr):
        for j in range(nc):
            val = pv_val.values[i, j]
            n   = int(pv_n.values[i, j])
            if not np.isnan(val) and n > 0:
                c = "white" if val > vmin + (vmax - vmin) * 0.6 else "black"
                ax.text(j, i, f"{val:.0f}%\n(n={n})",
                        ha="center", va="center", fontsize=8, color=c)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.04)
    cb.set_label(cbar_label, fontsize=9)
    ax.set_title(title, fontsize=12, pad=10)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Saved → {out_path}")
    plt.close(fig)


# ── Fig 1: hydro × acid → CO2 conversion ─────────────────────────────────────

def plot_conv_heatmap(df: pd.DataFrame, out_dir: Path) -> None:
    sub = df[df["co2_conv"].between(0.1, 100, inclusive="both")].copy()
    sub = sub[sub["hydro"] != "Other/Unknown"]

    pv = sub.groupby(["hydro", "acid"])["co2_conv"]
    draw_heatmap(
        pv.mean().unstack(fill_value=np.nan),
        pv.count().unstack(fill_value=0),
        title="CO₂ Hydrogenation: CO₂ Conversion\n加氢组分 × 芳构化组分（分子筛）",
        cbar_label="Mean CO₂ Conversion (%)",
        vmin=0, vmax=55, cmap="Blues",
        out_path=out_dir / "co2_bifunc_heatmap_conversion.png",
    )


# ── Fig 2: hydro × acid → aromatic selectivity ───────────────────────────────

def plot_aromatic_heatmap(df: pd.DataFrame, out_dir: Path) -> None:
    sub = df[df["aromatic_sel_pct"].between(0.1, 100, inclusive="both")].copy()
    sub = sub[sub["hydro"] != "Other/Unknown"]

    pv = sub.groupby(["hydro", "acid"])["aromatic_sel_pct"]
    draw_heatmap(
        pv.mean().unstack(fill_value=np.nan),
        pv.count().unstack(fill_value=0),
        title="CO₂→Aromatics: Aromatic Selectivity\n加氢组分 × 芳构化组分（分子筛）",
        cbar_label="Mean Aromatic Selectivity (%)",
        vmin=0, vmax=80, cmap="YlOrRd",
        out_path=out_dir / "co2_bifunc_heatmap_aromatic.png",
    )


# ── Fig 3: Stripplot — CO2 conv by hydro component ───────────────────────────

HYDRO_PALETTE = {
    "Cu":             "#1f77b4",
    "Fe":             "#d62728",
    "In₂O₃":          "#ff7f0e",
    "In₂O₃-ZnO/ZrO₂": "#e08020",
    "ZnO-ZrO₂":       "#2ca02c",
    "ZnO":            "#98df8a",
    "ZnCrOx":         "#17becf",
    "Pd":             "#9467bd",
    "Rh":             "#e377c2",
    "Co":             "#8c564b",
    "Ni":             "#7f7f7f",
    "Au":             "#bcbd22",
    "Pt":             "#dbdb8d",
}

def plot_strip(df: pd.DataFrame, out_dir: Path) -> None:
    sub = df[df["co2_conv"].between(0.1, 100)].copy()
    sub = sub[sub["hydro"] != "Other/Unknown"]

    # Mark whether paired with a zeolite or not
    sub["has_zeolite"] = sub["acid"].apply(lambda a: a != "No zeolite")

    order = (sub.groupby("hydro")["co2_conv"]
               .median().sort_values(ascending=False).index.tolist())

    fig, ax = plt.subplots(figsize=(12, 6))
    rng = np.random.default_rng(42)

    for i, hydro in enumerate(order):
        grp = sub[sub["hydro"] == hydro]
        color = HYDRO_PALETTE.get(hydro, "#aaaaaa")

        # With zeolite: filled markers
        for has_z, marker, alpha, edge in [(True, "o", 0.8, "white"),
                                            (False, "D", 0.5, color)]:
            pts = grp[grp["has_zeolite"] == has_z]["co2_conv"].dropna()
            if len(pts):
                jitter = rng.uniform(-0.3, 0.3, len(pts))
                ax.scatter(pts, i + jitter, color=color, marker=marker,
                           s=45, alpha=alpha, edgecolors=edge, linewidths=0.5)

        med = grp["co2_conv"].median()
        ax.plot([med], [i], marker="|", markersize=22,
                color="black", markeredgewidth=2.5)
        ax.text(101.5, i, f"n={len(grp)}", va="center", fontsize=8, color="#555")

    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order, fontsize=10)
    ax.set_xlabel("CO₂ Conversion (%)", fontsize=12)
    ax.set_title("CO₂ Hydrogenation: Conversion by 加氢组分\n"
                 "● with zeolite  ◆ without zeolite  | = median", fontsize=12)
    ax.set_xlim(-2, 110)
    ax.axvline(20, color="grey", lw=0.8, ls="--", alpha=0.5)
    ax.axvline(40, color="grey", lw=0.8, ls="--", alpha=0.5)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    out = out_dir / "co2_bifunc_strip_conversion.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.close(fig)


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame) -> None:
    print("\n=== 加氢组分 distribution (all CO₂ units) ===")
    print(df["hydro"].value_counts().to_string())
    print("\n=== 芳构化组分 distribution ===")
    print(df["acid"].value_counts().to_string())
    print("\n=== 加氢组分 × 芳构化组分 with conv data ===")
    sub = df[df["co2_conv"].between(0.1, 100)]
    print(sub.groupby(["hydro","acid"])["co2_conv"].agg(["mean","count"]).to_string(float_format="{:.1f}".format))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "figures"))
    args = ap.parse_args()
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)

    df = load()
    print(f"Loaded {len(df)} CO₂ units, classified into functional components.")
    print_summary(df)

    plot_conv_heatmap(df, out_dir)
    plot_aromatic_heatmap(df, out_dir)
    plot_strip(df, out_dir)

if __name__ == "__main__":
    main()

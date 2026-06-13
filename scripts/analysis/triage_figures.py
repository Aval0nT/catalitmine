"""triage_figures.py — caption-driven gold-set triage for figure digitization.

Question answered: of the corpus's performance figures, WHICH ones — if
digitized — would JOIN against the catalyst PROPERTY records already in the
DB to form structure–activity (SA) records? Digitizing all 148 line/scatter
figures is wasteful; the human gate costs time per figure. This ranks them so
the gate is spent on the ~20–40 that actually close SA records.

Inputs (all already materialized, no API, no GPU):
  outputs/reports/figure_scope.jsonl                  caption typing (scope_figures.py)
  data/05_normalized/catalyst_records_<latest>.jsonl  per-catalyst property records
  figures/all_charts/<slug>/<slug>.captions.json      (via figure_scope captions)

A figure yields an SA record two ways, both scored:
  (1) SELF-CONTAINED — the figure's own axis is a structural sweep
      ("selectivity vs Si/Al"): scope typed it structure_activity. The figure
      alone is an SA record once digitized.
  (2) JOIN — a performance figure (y = conversion/selectivity/yield) whose
      plotted catalysts have PROPERTY records in the same paper; digitizing
      the performance + joining the stored property = SA record.

Catalyst matching is REVERSE and WITHIN-PAPER: we take each property-bearing
catalyst label the paper already has in the DB and look for it in the figure's
caption (normalized, word-boundary). Matching known labels INTO free text is
far more precise than NER-ing unknown names out of it, and staying within one
paper sidesteps cross-paper homonyms (every paper has its own "H-ZSM-5").

Optional geometry/chartness pass (--sweep, needs the lineformer_hf model):
captions mistype heavily — reaction schemes, process diagrams and bar charts
leak into "line/scatter". Running the local LineFormer over the A+B
line/scatter figures gives a far better signal: ≥3 traces ⇒ real multi-line
chart; 0 traces ⇒ almost always a non-chart (scheme/diagram) or a bar chart,
NOT a marker scatter (verified by eye on this corpus). This both corrects the
digitization route per figure and answers the MarkerFormer go/no-go (how many
high-value figures are the scatter dead-zone LineFormer can't read).

Output:
  outputs/reports/figure_triage_<date>.jsonl   one row per high-value figure
  outputs/reports/figure_triage_<date>.md      human-readable ranked report
  console: tier counts + geometry buckets (incl. the line/scatter pool that
           the MarkerFormer go/no-go decision rides on)
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "analysis"))
from build_catalyst_records import norm_label  # reuse the canonical normalizer

SCOPE = ROOT / "outputs" / "reports" / "figure_scope.jsonl"
RECORDS_GLOB = str(ROOT / "data" / "05_normalized" / "catalyst_records_*.jsonl")

# attribute KEYS that denote a structural / textural / acidity PROPERTY (the
# "structure" half of structure–activity). Performance and reaction-condition
# attributes (conversion, selectivity, STY, temperature, pressure, GHSV, …)
# are deliberately excluded — they are the activity half or the x-condition.
STRUCT_ATTR = [
    "si_al", "si/al", "sio2_al2o3", "bet", "surface_area", "pore",
    "bronsted", "lewis", "bas_las", "las_", "_las", "acid", "acidity",
    "crystallin", "loading", "topology", "composition", "channel",
    "framework", "metal_content", "dispersion", "particle", "coverage",
    "monolayer", "proximity",
]
# substrings that, if present, VETO a structural reading (these keys carry
# performance/condition semantics even when they brush a struct keyword)
NOT_STRUCT = ["conversion", "selectiv", "yield", "_pct", "temperature",
              "pressure", "ghsv", "whsv", "contact", "space_time", "tos",
              "h2_co2", "h2_co", "ratio_h", "methane", "ethylene", "aromatics",
              "propylene", "co_", "_co", "formation"]


def is_struct_attr(key: str) -> bool:
    k = key.lower()
    if any(v in k for v in NOT_STRUCT):
        return False
    return any(s in k for s in STRUCT_ATTR)


def latest_records() -> Path:
    files = sorted(glob.glob(RECORDS_GLOB))
    if not files:
        raise SystemExit(f"no catalyst records under {RECORDS_GLOB}")
    return Path(files[-1])


def norm_text(s: str) -> str:
    """Lowercase, unify hyphens, collapse whitespace — for substring search."""
    s = norm_label(s).lower()
    return re.sub(r"\s+", " ", s)


def label_in_caption(variants: list[str], cap_norm: str) -> str | None:
    """Return the matched variant if any catalyst label appears in the caption
    as a standalone token, else None. Skips labels too short/generic to be safe
    (<3 normalized chars), which would false-match prose.

    The boundary is whitespace/string-edge — NOT any non-alphanumeric — so a
    shorter label cannot match as a fragment of a longer chemically distinct
    catalyst joined by '-' or '/'. Without this, the property record "C-HZSM-5"
    would match inside "Zn-C-HZSM-5" in a caption and silently graft the
    non-Zn parent's BET/acidity onto a figure of the Zn-loaded variant (a
    different sample). Found by adversarial review 2026-06-13."""
    for v in variants:
        nv = norm_text(v)
        if len(nv.replace("-", "").replace(" ", "")) < 3:
            continue
        # token boundary: start/space before, end/space after. The label may
        # carry a trailing closing paren / comma in prose (e.g. "ZSM-5(25),"),
        # so allow those specific punctuation neighbours but never '-' or '/'.
        if re.search(rf"(?:^|\s|\(){re.escape(nv)}(?:$|[\s,.;:)])", cap_norm):
            return v
    return None


def tier(self_contained: bool, n_matched: int, pool: int) -> tuple[str, str]:
    """(tier, why). A/B are CAPTION-EVIDENCED (a named catalyst matched a
    property record, or the figure's own axis is a structural sweep); C is
    SPECULATIVE or coverage-limited. The split keeps the human gate on figures
    with real JOIN evidence rather than on every figure that merely lives in a
    property-rich paper.

    Revised 2026-06-13 after adversarial review: self_contained alone no longer
    auto-promotes to A — scope_figures mistypes TEA plots and synthesis schemes
    as 'structure_activity', so a structural-axis claim with zero caption match
    is only a (flagged) B; and the old 'pool>=3, zero match' tier-B rule
    (40/74 figures, mostly review-paper schematics) is demoted to C-speculative."""
    if n_matched >= 2 or (self_contained and n_matched >= 1):
        return "A", (f"caption names {n_matched} catalyst(s) with property records"
                     + (" on a structural axis" if self_contained else ""))
    if n_matched == 1:
        return "B", "caption names 1 catalyst with a property record"
    if self_contained and pool > 0:
        return "B", "structural-axis per caption typing — UNVERIFIED (scope may mistype)"
    if pool >= 3:
        return "C", f"speculative: no caption match; paper has {pool} property catalysts"
    if pool >= 1:
        return "C", f"paper has only {pool} property catalyst(s), no caption match"
    return "C", "coverage gap: no property records in this paper to join against"


def lineformer_traces(figures: list[str]) -> dict[str, int | None]:
    """Run the local HF LineFormer over each figure → count of real traces
    (series with ≥5 points). None if the file is not found. Geometry/chartness
    signal for the route + the scatter go/no-go; see module docstring."""
    sys.path.insert(0, str(ROOT / "scripts" / "extraction" / "lineformer_port"))
    import cv2
    from line_postproc import masks_to_dataseries
    from lineformer_hf_infer import get_instance_masks, load_model

    model = load_model(ROOT / "models" / "lineformer_hf")
    out: dict[str, int | None] = {}
    for fig in figures:
        hits = glob.glob(str(ROOT / "figures" / "all_charts" / "*" / fig))
        if not hits:
            out[fig] = None
            continue
        masks, _ = get_instance_masks(model, cv2.imread(hits[0]))
        out[fig] = sum(1 for s in masks_to_dataseries(masks) if len(s) >= 5)
    return out


def route_for(shape: str | None, traces: int | None, mf_target: bool | None) -> str:
    """Digitization route. A ≥3 trace count does NOT prove a LINE chart —
    LineFormer chains dense scatter markers into spurious traces — so the
    line-vs-scatter call comes from the visual census (mf_target), not the
    trace count (review fix 2026-06-13: the trace-only heuristic wrongly
    cleared the high-value pool of scatter)."""
    if mf_target:
        return "MarkerFormer (disconnected-marker scatter; LineFormer fails)"
    if shape == "bar":
        return "bar_reader"
    if traces is None:
        return "lineformer? (not swept)"
    if traces >= 3:
        return "lineformer (line — census-confirmed or unreviewed)"
    return "review: 0-2 traces — bar/scheme/non-chart, not a line"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-06-13", help="output filename stamp")
    ap.add_argument("--sweep", action="store_true",
                    help="run local LineFormer over A+B line/scatter figures "
                         "for a geometry/chartness correction (needs the model)")
    args = ap.parse_args()

    scope = [json.loads(l) for l in open(SCOPE)]
    recs = [json.loads(l) for l in open(latest_records())]

    # per-paper pool of property-bearing catalysts
    paper_props: dict[str, list[dict]] = {}
    struct_attr_seen: Counter = Counter()
    for r in recs:
        props = {a: v for a, v in r.get("attributes", {}).items() if is_struct_attr(a)}
        if not props:
            continue
        struct_attr_seen.update(props.keys())
        paper_props.setdefault(r["paper_doi"], []).append({
            "label": r["catalyst_label"],
            "variants": r.get("label_variants", [r["catalyst_label"]]),
            "props": sorted(props.keys()),
        })

    hv = [s for s in scope if s["type"] in ("activity", "structure_activity", "mixed")]

    rows = []
    for s in hv:
        doi = s["doi"]
        cap = s.get("caption", "")
        cap_norm = norm_text(cap)
        pool = paper_props.get(doi, [])
        matched = []
        for c in pool:
            hit = label_in_caption(c["variants"], cap_norm)
            if hit:
                matched.append({"label": c["label"], "matched_on": hit, "props": c["props"]})
        self_contained = s["type"] == "structure_activity"
        t, why = tier(self_contained, len(matched), len(pool))
        # property kinds reachable: from MATCHED catalysts when we have caption
        # evidence (a confirmed figure-level join); otherwise the whole-paper
        # pool union, flagged as such so the report does not imply a join the
        # matcher never established (review fix 2026-06-13).
        if matched:
            reachable = sorted({p for c in matched for p in c["props"]})
            reach_scope = "matched"
        else:
            reachable = sorted({p for c in pool for p in c["props"]})
            reach_scope = "pool-wide (no caption match — figure catalysts unconfirmed)"
        rows.append({
            "figure": s["figure"], "doi": doi,
            "fig_type": s["type"], "shape": s.get("shape"),
            "tier": t, "why": why,
            "evidenced": len(matched) > 0 or self_contained,
            "self_contained_sa": self_contained,
            "n_caption_matched": len(matched),
            "n_paper_property_catalysts": len(pool),
            "matched_catalysts": matched,
            "reachable_properties": reachable,
            "reachable_scope": reach_scope,
            "caption": cap[:300],
        })

    order = {"A": 0, "B": 1, "C": 2}
    rows.sort(key=lambda r: (order[r["tier"]], -r["n_caption_matched"],
                             -r["n_paper_property_catalysts"]))

    # optional geometry/chartness correction on the A+B line/scatter pool
    sweep: dict[str, int | None] = {}
    if args.sweep:
        targets = [r["figure"] for r in rows
                   if r["tier"] in ("A", "B") and r["shape"] == "line/scatter"]
        sweep = lineformer_traces(targets)
    # visual scatter census (scatter_census_<date>.json, list of figure names
    # that are true MarkerFormer targets — disconnected-marker SA scatter that
    # LineFormer cannot read). Produced by the census workflow; the trace count
    # alone cannot make this call.
    census_path = ROOT / "outputs" / "reports" / f"scatter_census_{args.date}.json"
    mf_targets: set[str] = set()
    if census_path.exists():
        mf_targets = set(json.loads(census_path.read_text()).get("markerformer_targets", []))
    for r in rows:
        r["lf_traces"] = sweep.get(r["figure"])
        r["markerformer_target"] = r["figure"] in mf_targets
        r["route"] = route_for(r["shape"], r["lf_traces"], r["markerformer_target"])

    # ---- write artifacts ----
    out_jsonl = ROOT / "outputs" / "reports" / f"figure_triage_{args.date}.jsonl"
    out_jsonl.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")

    by_tier = Counter(r["tier"] for r in rows)
    ab = [r for r in rows if r["tier"] in ("A", "B")]
    route_ab = Counter(r["route"] for r in ab)
    evidenced = [r for r in ab if r["n_caption_matched"] > 0]
    mf = [r for r in rows if r.get("markerformer_target")]

    # coverage: a figure can only tier above C if its paper has property records
    fig_dois = {s["doi"] for s in scope}
    no_pool = sorted(fig_dois - set(paper_props))
    cov_capped = sum(1 for r in rows if r["n_paper_property_catalysts"] == 0)

    md = [f"# Figure triage — {args.date}", "",
          f"High-value (tier A+B, caption-evidenced): **{len(ab)}** of {len(rows)} "
          f"performance figures ({len(scope)} crops total). "
          f"Hard caption-match subset: **{len(evidenced)}**.", "",
          f"- Tier A (≥2 matches, or structural-axis + match): {by_tier['A']}",
          f"- Tier B (1 match, or unverified structural-axis): {by_tier['B']}",
          f"- Tier C (speculative / coverage-gap): {by_tier['C']}", "",
          "### Coverage caveat", "",
          f"{len(set(paper_props))} of {len(fig_dois)} papers with figures have any "
          f"property records; {len(no_pool)} papers have none, so {cov_capped} "
          "performance figures are capped at tier C by CORPUS COVERAGE, not figure "
          "quality. Tier C ≠ 'weak figure' — it is mostly 'no joinable property "
          "record (yet)'.", "",
          "## Digitization route for the A+B pool", ""]
    for rt, n in route_ab.most_common():
        md.append(f"- {rt}: {n}")
    md += ["", f"**MarkerFormer go/no-go:** the visual census found **{len(mf)}** "
           "disconnected-marker scatter figures across the high-value pool "
           "(LineFormer cannot read these; bar_reader cannot either). "
           + ("See the scatter_census file." if mf else
              "Census file not yet loaded — run the census workflow."), "",
           "## Tier A+B figures", ""]
    for r in ab:
        mc = ", ".join(m["label"] for m in r["matched_catalysts"]) or "—"
        tr = "" if r["lf_traces"] is None else f", {r['lf_traces']} traces"
        flag = "  ⚠MarkerFormer" if r.get("markerformer_target") else ""
        md.append(f"### [{r['tier']}] {r['figure']}  ({r['fig_type']}/{r['shape']}{tr}){flag}")
        md.append(f"- route: {r['route']}")
        md.append(f"- why: {r['why']}")
        md.append(f"- caption-matched catalysts: {mc}")
        md.append(f"- paper property pool: {r['n_paper_property_catalysts']} "
                  f"| reachable props ({r['reachable_scope']}): "
                  f"{', '.join(r['reachable_properties']) or '—'}")
        md.append(f"- caption: {r['caption'][:200]}")
        md.append("")
    out_md = ROOT / "outputs" / "reports" / f"figure_triage_{args.date}.md"
    out_md.write_text("\n".join(md))

    # ---- console summary ----
    print(f"high-value figures (scope activity/SA/mixed): {len(rows)}")
    print(f"  tier A {by_tier['A']} | tier B {by_tier['B']} | tier C {by_tier['C']}")
    print(f"  caption-evidenced (hard JOIN signal): {len(evidenced)}")
    print(f"  coverage: {len(no_pool)}/{len(fig_dois)} figure-papers have NO property "
          f"records → {cov_capped} figures capped at tier C by coverage")
    print(f"\nA+B pool = {len(ab)} figures, by digitization route:")
    for rt, n in route_ab.most_common():
        print(f"  {n:3d}  {rt}")
    if census_path.exists():
        print(f"\nMarkerFormer go/no-go (visual census): {len(mf)} disconnected-marker "
              "scatter figures in the high-value pool that neither LineFormer nor "
              "bar_reader can read.")
    else:
        print("\n(no scatter_census file yet — MarkerFormer verdict pending census)")
    print(f"\nstructural attributes counted as 'property' (audit): "
          f"{dict(struct_attr_seen.most_common())}")
    print(f"\nwrote {out_jsonl.name} + {out_md.name}")


if __name__ == "__main__":
    main()

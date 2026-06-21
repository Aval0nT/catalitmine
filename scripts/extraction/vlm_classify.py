"""vlm_classify.py — VLM figure typing (replaces caption-keyword classification).

scope_figures.py types figures from CAPTION TEXT with substring keywords, which
conflates "the caption mentions conversion" with "the figure plots conversion"
(FT-IR spectra → mixed) and is blind to the pixels (reaction schemes → activity,
bar charts → line/scatter). This module asks a vision model to look at the IMAGE
instead — the unambiguous signal: are there axes, are the points connected lines
or discrete markers, is it a diagram.

Cheap, one-time, cached: the whole 974-figure corpus is ~$1-6 depending on model
(Haiku vs Sonnet); results land in a jsonl the human gate confirms. Later, these
labels can train a local classifier (the LLM-free endgame for this task).

Robust to SDK version: prompts for JSON and extracts it (no output_config), the
same pattern as chart_extractor.VisionChartExtractor.

Pilot:  venv/bin/python scripts/extraction/vlm_classify.py --pilot [--model sonnet]
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
MODELS = {"haiku": "claude-haiku-4-5", "sonnet": "claude-sonnet-4-6",
          "opus": "claude-opus-4-8"}
MAX_EDGE = 1280  # long-edge cap: keeps marker/line detail, trims vision-token cost


def _load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if not os.environ.get(k.strip(), "").strip():
                    os.environ[k.strip()] = v.strip()


_PROMPT = """You are typing a figure from a heterogeneous-catalysis paper (methanol-to-aromatics / CO2-to-aromatics). Look at the IMAGE itself — do not rely on any caption.

Return ONLY a JSON object:
{
  "figure_kind": "chart|scheme|micrograph|spectrum|photo|other",
  "n_panels": <int>,
  "panel_geometries": [<"line"|"scatter"|"bar"|"none", one per data-plot panel>],
  "is_performance": <bool>,
  "has_disconnected_scatter": <bool>,
  "confidence": "high|medium|low",
  "note": "<≤12 words>"
}

Definitions — read carefully:
- figure_kind:
  - "chart": has plot axes with data (line/scatter/bar).
  - "scheme": reaction mechanism, pathway, process flow, molecular-structure diagram with arrows — NO data axes.
  - "micrograph": SEM/TEM/microscopy images.
  - "spectrum": XRD / FT-IR / Raman / NMR / UV-vis — a spectral trace (intensity vs wavelength/angle/shift), NOT catalytic performance.
  - "photo": photograph of equipment/samples.
- panel_geometries: one entry per panel that is a data plot. For each, decide:
  - "line": data points joined by continuous lines (curves).
  - "scatter": DISCRETE markers (circles/squares/triangles) that are NOT joined by lines, or joined only by a thin dashed trend/fit line. The data IS the markers.
  - "bar": vertical or horizontal bars.
  - "none": that panel is not a data plot (image/scheme inset).
  A figure with no data plots → [].
- is_performance: true only if a panel plots CATALYTIC PERFORMANCE (conversion, selectivity, yield, productivity, deactivation/stability vs time/condition). Spectra, XRD, micrographs, schemes → false.
- has_disconnected_scatter: true if ANY panel is a scatter of discrete markers NOT connected by a data line (these are the panels a line-tracer cannot read). Connected-marker line plots → false.

Be decisive. If a composite mixes panel types, list each geometry. JSON only, no prose."""


def _b64_image(path: Path) -> tuple[str, str]:
    from PIL import Image

    img = Image.open(path).convert("RGB")
    w, h = img.size
    if max(w, h) > MAX_EDGE:
        s = MAX_EDGE / max(w, h)
        img = img.resize((round(w * s), round(h * s)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode(), "image/png"


_client = None


def _client_lazy():
    global _client
    if _client is None:
        from anthropic import Anthropic
        for var in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_BASE_URL"):
            os.environ.pop(var, None)
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise SystemExit("ANTHROPIC_API_KEY not set in .env/environment")
        _client = Anthropic(api_key=key, base_url="https://api.anthropic.com")
    return _client


def _classify_with_usage(path: Path, model: str = "haiku") -> tuple[dict, tuple[int, int]]:
    """classify() but also returns (input_tokens, output_tokens) for cost tracking."""
    data, media = _b64_image(path)
    try:
        resp = _client_lazy().messages.create(
            model=MODELS.get(model, model), max_tokens=400,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                 "media_type": media, "data": data}},
                {"type": "text", "text": _PROMPT}]}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
        usage = (resp.usage.input_tokens, resp.usage.output_tokens)
    except Exception as e:
        return {"error": f"api: {e}"}, (0, 0)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"error": "no JSON", "raw": text[:200]}, usage
    try:
        return json.loads(m.group(0)), usage
    except json.JSONDecodeError as e:
        return {"error": f"json: {e}", "raw": text[:200]}, usage


def classify(path: Path, model: str = "haiku") -> dict:
    return _classify_with_usage(path, model)[0]


# ── pilot validation set: figures whose labels we verified by eye this session ──
# expected: (figure_kind, is_performance, has_disconnected_scatter)
PILOT = [
    ("10.1016_j.mcat.2022.112702_fig06_p5",      "chart",    True,  False),  # deactivation lines
    ("10.1021_acscatal.5b00192_fig09_p4",        "chart",    True,  False),  # multi-panel lines
    ("10.1016_j.catcom.2009.04.004_fig03_p2",    "chart",    True,  False),  # stacked sel. bars
    ("10.1002_anie.201103657_fig36_p15",         "chart",    True,  False),  # MeOH-converted bars
    ("10.1016_j.jcat.2018.03.032_fig15_p47",     "chart",    True,  True),   # dense marker scatter
    ("10.1002_anie.201103657_fig39_p17",         "chart",    True,  True),   # sparse SA scatter
    ("10.1002_anie.201103657_fig09_p3",          "scheme",   False, False),  # process flow diagram
    ("10.1021_acs.chemrev.9b00723_fig30_p31",    "scheme",   False, False),  # CO2→MeOH pathways
    ("10.1016_s1872-2067(22)64209-8_fig17_p10",  "scheme",   False, False),  # alkene/arene cycle
    ("10.1016_s1872-2067(22)64209-8_fig19_p12",  "scheme",   False, False),  # reaction equations
    ("10.1021_acscatal.3c01332_fig19_p11",       "spectrum", False, False),  # FT-IR (caption said "conversion")
    ("10.1016_j.mtsust.2023.100364_fig12_p8",    "spectrum", False, False),  # UV-vis stacked
]


def run_pilot(model: str) -> None:
    import glob

    print(f"\n=== VLM pilot · model={MODELS.get(model, model)} ===\n")
    kind_ok = perf_ok = scat_ok = all3 = total = 0
    for stem, e_kind, e_perf, e_scat in PILOT:
        hits = glob.glob(str(ROOT / "figures" / "all_charts" / "*" / f"{stem}.png"))
        if not hits:
            print(f"  (missing) {stem}")
            continue
        r = classify(Path(hits[0]), model)
        total += 1
        if "error" in r:
            print(f"  ERR {stem}: {r['error']}")
            continue
        k, p, s = r.get("figure_kind"), r.get("is_performance"), r.get("has_disconnected_scatter")
        kk, pp, ss = k == e_kind, p == e_perf, s == e_scat
        kind_ok += kk; perf_ok += pp; scat_ok += ss; all3 += (kk and pp and ss)
        flag = lambda ok: "✓" if ok else "✗"
        geom = ",".join(r.get("panel_geometries", []))
        print(f"  kind{flag(kk)}{k:9} perf{flag(pp)}{str(p):5} scat{flag(ss)}{str(s):5} "
              f"[{geom[:18]}]  {stem[:42]}")
        if not (kk and pp and ss):
            print(f"        expected kind={e_kind} perf={e_perf} scat={e_scat} | note: {r.get('note','')}")
    print(f"\n  figure_kind:          {kind_ok}/{total}")
    print(f"  is_performance:       {perf_ok}/{total}")
    print(f"  disconnected_scatter: {scat_ok}/{total}  (the subtle scatter/line call)")
    print(f"  ALL-3 correct:        {all3}/{total}")


SCOPE = ROOT / "outputs" / "reports" / "figure_scope.jsonl"
OUT_JSONL = ROOT / "outputs" / "reports" / "vlm_scope.jsonl"


def _resolve(figure: str) -> Optional[str]:
    import glob
    hits = glob.glob(str(ROOT / "figures" / "all_charts" / "*" / figure))
    return hits[0] if hits else None


def run_batch(model: str, scope: str) -> None:
    """Classify a set of figures, caching to vlm_scope.jsonl (resumable)."""
    import glob

    rows = [json.loads(l) for l in open(SCOPE)]
    if scope == "highvalue":
        targets = [r for r in rows if r["type"] in ("activity", "structure_activity", "mixed")]
    else:
        targets = rows
    done = {}
    if OUT_JSONL.exists():
        for l in open(OUT_JSONL):
            d = json.loads(l)
            done[d["figure"]] = d
    todo = [r for r in targets if r["figure"] not in done]
    print(f"VLM typing · model={MODELS.get(model, model)} · {len(targets)} target(s), "
          f"{len(done)} cached, {len(todo)} to run\n")

    in_tok = out_tok = 0
    with open(OUT_JSONL, "a") as fh:
        for i, r in enumerate(todo, 1):
            path = _resolve(r["figure"])
            if not path:
                rec = {"figure": r["figure"], "doi": r["doi"], "error": "file not found"}
            else:
                cls, usage = _classify_with_usage(Path(path), model)
                in_tok += usage[0]; out_tok += usage[1]
                rec = {"figure": r["figure"], "doi": r["doi"],
                       "caption_type": r["type"], "caption_shape": r.get("shape"), **cls}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 20 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}  (in {in_tok} / out {out_tok} tok so far)")
    cost = in_tok * 1e-6 * 1.0 + out_tok * 1e-6 * 5.0  # Haiku $1/$5 per MTok
    print(f"\nran {len(todo)} new · tokens in={in_tok} out={out_tok} · "
          f"cost this run ≈ ${cost:.3f}")
    _summarize()


def _summarize() -> None:
    from collections import Counter
    rows = [json.loads(l) for l in open(OUT_JSONL)]
    ok = [r for r in rows if "error" not in r]
    kinds = Counter(r.get("figure_kind") for r in ok)
    perf = sum(1 for r in ok if r.get("is_performance"))
    scat = [r for r in ok if r.get("has_disconnected_scatter")]
    geom = Counter(g for r in ok for g in r.get("panel_geometries", []))
    print(f"\n=== vlm_scope.jsonl summary ({len(ok)} typed, {len(rows)-len(ok)} errors) ===")
    print(f"figure_kind: {dict(kinds)}")
    print(f"panel geometries (panel-level): {dict(geom)}")
    print(f"is_performance: {perf}/{len(ok)}")
    print(f"disconnected-scatter figures (MarkerFormer targets): {len(scat)}")
    for r in scat:
        print(f"   - {r['figure']}")
    # disagreements vs caption shape
    flip = [r for r in ok if r.get("caption_shape") == "line/scatter"
            and "bar" in r.get("panel_geometries", []) and "line" not in r.get("panel_geometries", [])
            and "scatter" not in r.get("panel_geometries", [])]
    nonchart = [r for r in ok if r.get("caption_type") in ("activity", "structure_activity", "mixed")
                and r.get("figure_kind") != "chart"]
    print(f"caption said line/scatter but VLM says bar-only: {len(flip)}")
    print(f"caption said performance-figure but VLM says non-chart: {len(nonchart)}")


def main() -> None:
    _load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--batch", choices=["highvalue", "all"],
                    help="classify high-value (activity/SA/mixed) or all figures")
    ap.add_argument("--summary", action="store_true", help="re-print vlm_scope summary")
    ap.add_argument("--model", default="haiku", choices=list(MODELS))
    ap.add_argument("--image", help="classify a single image")
    args = ap.parse_args()
    if args.image:
        print(json.dumps(classify(Path(args.image), args.model), indent=2, ensure_ascii=False))
    elif args.pilot:
        run_pilot(args.model)
    elif args.batch:
        run_batch(args.model, args.batch)
    elif args.summary:
        _summarize()
    else:
        raise SystemExit("pass --pilot, --batch, --summary, or --image")


if __name__ == "__main__":
    main()

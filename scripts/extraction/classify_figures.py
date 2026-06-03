"""
classify_figures.py — gate figures BY TYPE before any data extraction.

Most figures in a catalysis paper are characterisation (SEM/TEM/XRD/Raman/
NH3-TPD/pyridine-IR/N2-physisorption/NMR/XPS), NOT activity data. Extracting
"data" from those is meaningless. This classifier labels each panel so the
pipeline only sends genuine activity / structure-activity panels downstream.

Categories (per panel):
  - activity                     : measured conversion / selectivity / yield /
                                   productivity / stability(TOS) / regeneration /
                                   product distribution
  - structure_activity_relation  : a catalyst descriptor (Si/Al, acidity, loading)
                                   plotted against a performance metric
  - characterization             : SEM/TEM/XRD/Raman/TPD/IR/NMR/physisorption/XPS
  - reaction_scheme / other

Output: outputs/charts/<image>.figtype.json  + a summary table.

  python3 scripts/extraction/classify_figures.py --dir figures/charts_test
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if not os.environ.get(k, "").strip():
                    os.environ[k] = v

_load_env()
MODEL = os.environ.get("CATALITMINE_VISION_MODEL", "claude-sonnet-4-5")

PROMPT = """You classify a scientific figure from a heterogeneous-catalysis paper.

For EACH panel (a, b, c… or a single panel), classify its type. Be strict:
SEM, TEM, XRD, Raman, IR/FTIR, pyridine-IR, NH3-TPD, H2-TPR, N2 physisorption,
NMR, XPS, UV-vis, TGA are CHARACTERIZATION — never "activity".

Types:
- "activity": axes show measured catalytic performance — conversion, selectivity,
  yield, space-time yield, productivity, stability/time-on-stream, regeneration
  cycles, or product distribution (bar chart of product fractions).
- "structure_activity_relation": a catalyst descriptor (Si/Al, acid density,
  metal loading, BET, coverage) on one axis vs a performance metric on the other.
- "characterization": material structure/texture/acidity probes (the techniques
  listed above). Give the technique as subtype.
- "reaction_scheme": mechanism or scheme drawing.
- "other".

Return JSON only:
{
  "panels": [
    {"panel": "a", "type": "...", "subtype": "<technique or metric>",
     "x_axis": "...", "y_axis": "...", "reason": "<short>"}
  ]
}
Read axis labels verbatim. If unsure between activity and characterization, look
at the y-axis: intensity/absorbance/signal/counts = characterization."""


def classify(path: Path, client) -> dict:
    media = mimetypes.guess_type(str(path))[0] or "image/png"
    data = base64.standard_b64encode(path.read_bytes()).decode()
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=1500,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                 "media_type": media, "data": data}},
                {"type": "text", "text": PROMPT}]}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
    except Exception as e:
        return {"error": f"api: {e}"}
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        return {"error": "no JSON"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {"error": f"json: {e}"}


ACTIVITY_TYPES = {"activity", "structure_activity_relation"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Classify figures by type (gate before extraction)")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", default=str(ROOT / "outputs" / "charts"))
    ap.add_argument("--min-size", type=int, default=120)
    args = ap.parse_args()

    from anthropic import Anthropic
    for var in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_BASE_URL"):
        os.environ.pop(var, None)
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY not set")
    client = Anthropic(api_key=key, base_url="https://api.anthropic.com")

    imgs = []
    for ext in ("*.png", "*.jpg", "*.jpeg"):
        imgs += sorted(Path(args.dir).glob(ext))
    try:
        from PIL import Image
        imgs = [p for p in imgs
                if min(Image.open(p).size) >= args.min_size]
    except Exception:
        pass

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Classifying {len(imgs)} figures with {MODEL}\n")
    print(f"{'figure':42s} {'panel':5s} {'type':28s} subtype")
    print("-" * 96)
    keep = []
    for img in imgs:
        res = classify(img, client)
        (out_dir / f"{img.stem}.figtype.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        if res.get("error"):
            print(f"{img.name[:42]:42s} ERROR {res['error']}")
            continue
        panels = res.get("panels", [])
        has_activity = any(p.get("type") in ACTIVITY_TYPES for p in panels)
        if has_activity:
            keep.append(img.name)
        for p in panels:
            tag = "✦" if p.get("type") in ACTIVITY_TYPES else " "
            print(f"{img.name[:42]:42s} {str(p.get('panel'))[:5]:5s} "
                  f"{tag}{str(p.get('type'))[:27]:27s} {str(p.get('subtype'))[:30]}")
    print("-" * 96)
    print(f"\n✦ figures with activity / structure-activity panels ({len(keep)}):")
    for k in keep:
        print(f"   {k}")
    print("\nOnly these should go to chart_extractor. The rest are characterization.")


if __name__ == "__main__":
    main()

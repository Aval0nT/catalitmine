"""
vision_chart.py — read catalysis performance plots with Claude vision (no GPU).

A zero-setup alternative / complement to the LineFormer route: send a chart image
to Claude and get back structured data — chart type, axis labels + units, and each
series mapped to its legend/catalyst name with (x, y) points. Runs on a Mac via the
Anthropic API we already use; no CUDA/MMDetection.

Strength: reads legends, axis labels, and units well (the curve→catalyst mapping that
the DL tools struggle with). Weakness: point coordinates are model estimates, less
precise than LineFormer's pixel-level extraction.

Usage:
  python3 scripts/analysis/vision_chart.py --image figures/charts_test/fig09.png
  python3 scripts/analysis/vision_chart.py --dir figures/charts_test --out outputs/reports
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
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

PROMPT = """You extract numerical data from a scientific catalysis plot image.

Read the figure carefully and return a JSON object only (no prose). If the image
contains multiple panels (a), (b), (c)…, return one entry per panel.

Schema:
{
  "panels": [
    {
      "panel": "a",                      // or null if single chart
      "chart_type": "line|scatter|bar",
      "x_axis": {"label": "...", "unit": "...", "min": 0, "max": 40},
      "y_axis": {"label": "...", "unit": "...", "min": 0, "max": 100},
      "series": [
        {
          "name": "<legend label = catalyst name>",
          "points": [{"x": <number>, "y": <number>}, ...]
        }
      ]
    }
  ],
  "confidence": "high|medium|low",
  "notes": "anything ambiguous (log axis, overlapping curves, unreadable legend)"
}

Rules:
- Use the legend text verbatim as each series "name" (this is the catalyst identity).
- Read tick values from the axes; estimate each point's (x, y) against them.
- Only include series/points you can actually see. Do not invent data.
- If you cannot read something, lower "confidence" and explain in "notes"."""


def _encode(path: Path) -> tuple[str, str]:
    media = mimetypes.guess_type(str(path))[0] or "image/png"
    data = base64.standard_b64encode(path.read_bytes()).decode()
    return media, data


def extract_image(path: Path, client) -> dict:
    media, data = _encode(path)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": media, "data": data}},
                {"type": "text", "text": PROMPT},
            ],
        }],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        return {"error": "no JSON in response", "raw": text[:500]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse failed: {e}", "raw": text[:500]}


def _summarize(name: str, result: dict) -> None:
    if "error" in result:
        print(f"  ✗ {name}: {result['error']}")
        return
    panels = result.get("panels", [])
    conf = result.get("confidence", "?")
    print(f"  ✓ {name}: {len(panels)} panel(s), confidence={conf}")
    for p in panels:
        sers = p.get("series", [])
        npts = sum(len(s.get("points", [])) for s in sers)
        xa = (p.get("x_axis") or {}).get("label", "?")
        ya = (p.get("y_axis") or {}).get("label", "?")
        names = ", ".join(s.get("name", "?") for s in sers)[:70]
        print(f"      panel {p.get('panel')}: {p.get('chart_type')} | "
              f"{xa} vs {ya} | {len(sers)} series, {npts} pts")
        print(f"        series: {names}")
    if result.get("notes"):
        print(f"        notes: {result['notes'][:120]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Read chart images with Claude vision")
    ap.add_argument("--image", help="Single image file")
    ap.add_argument("--dir", help="Folder of images (.png/.jpg)")
    ap.add_argument("--out", default=str(ROOT / "outputs" / "reports"),
                    help="Output folder for per-image JSON")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        raise SystemExit("ANTHROPIC_API_KEY not set in environment/.env")
    try:
        from anthropic import Anthropic
    except ImportError:
        raise SystemExit("pip install anthropic")
    # Use the real Anthropic endpoint with the user's own key. Clear proxy /
    # bearer env vars that some host shells inject (an empty ANTHROPIC_AUTH_TOKEN
    # becomes an illegal "Bearer " header; a proxy ANTHROPIC_BASE_URL won't
    # authenticate the user's key).
    for var in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_BASE_URL"):
        os.environ.pop(var, None)
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"],
                       base_url="https://api.anthropic.com")

    imgs: list[Path] = []
    if args.image:
        imgs.append(Path(args.image))
    if args.dir:
        for ext in ("*.png", "*.jpg", "*.jpeg"):
            imgs += sorted(Path(args.dir).glob(ext))
    if not imgs:
        raise SystemExit("pass --image or --dir")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Reading {len(imgs)} image(s) with {MODEL}\n")
    for img in imgs:
        if not img.exists():
            print(f"  ✗ {img.name}: not found")
            continue
        result = extract_image(img, client)
        _summarize(img.name, result)
        (out_dir / f"{img.stem}.vision.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON written to {out_dir}")


if __name__ == "__main__":
    main()

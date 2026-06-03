"""
chart_extractor.py — pluggable chart→data extraction (Branch A).

Defines a `ChartExtractor` interface + typed result objects, with a Claude-vision
backend that works today (no GPU). A second backend — a standalone, MMDetection-free
LineFormer in pure PyTorch — is being built on the `feat/lineformer-standalone`
branch and will plug in behind the same interface for a reproducible / self-hostable
path. The pipeline owns the interface; backends are swappable.

CLI (batch over a folder of figure images):
  python3 scripts/extraction/chart_extractor.py --dir figures/charts_test
  python3 scripts/extraction/chart_extractor.py --image fig.png --backend vision

Upstream: get figure PNGs with scripts/extraction/extract_figures.py.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Protocol

ROOT = Path(__file__).resolve().parents[2]


# ── env (clears host-injected proxy/bearer vars so the user's key hits the API) ─

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


# ── typed result objects ────────────────────────────────────────────────────

@dataclass
class Axis:
    label: Optional[str] = None
    unit: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None

@dataclass
class Series:
    name: str                      # legend label = catalyst identity
    points: list[dict] = field(default_factory=list)   # [{"x":..,"y":..}]

@dataclass
class Panel:
    panel: Optional[str] = None
    chart_type: Optional[str] = None
    x_axis: Axis = field(default_factory=Axis)
    y_axis: Axis = field(default_factory=Axis)
    series: list[Series] = field(default_factory=list)

@dataclass
class ChartExtraction:
    image: str
    backend: str
    model: Optional[str] = None
    panels: list[Panel] = field(default_factory=list)
    confidence: Optional[str] = None
    notes: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def n_points(self) -> int:
        return sum(len(s.points) for p in self.panels for s in p.series)


# ── backend interface ───────────────────────────────────────────────────────

class ChartExtractor(Protocol):
    name: str
    def extract(self, image_path: Path) -> ChartExtraction: ...


def _parse_panels(obj: dict) -> list[Panel]:
    panels = []
    for p in obj.get("panels", []):
        xa, ya = p.get("x_axis") or {}, p.get("y_axis") or {}
        panels.append(Panel(
            panel=p.get("panel"),
            chart_type=p.get("chart_type"),
            x_axis=Axis(xa.get("label"), xa.get("unit"), xa.get("min"), xa.get("max")),
            y_axis=Axis(ya.get("label"), ya.get("unit"), ya.get("min"), ya.get("max")),
            series=[Series(s.get("name", "?"), s.get("points", []))
                    for s in p.get("series", [])],
        ))
    return panels


# ── Vision backend (Claude) ─────────────────────────────────────────────────

_PROMPT = """You extract numerical data from a scientific catalysis plot image.

Return a JSON object only (no prose). If the image has multiple panels (a),(b),(c)…,
return one entry per panel.

{
  "panels": [{
    "panel": "a", "chart_type": "line|scatter|bar",
    "x_axis": {"label": "...", "unit": "...", "min": 0, "max": 40},
    "y_axis": {"label": "...", "unit": "...", "min": 0, "max": 100},
    "series": [{"name": "<legend label = catalyst name>",
                "points": [{"x": <number>, "y": <number>}]}]
  }],
  "confidence": "high|medium|low",
  "notes": "ambiguities: log axis, overlapping curves, unreadable legend, etc."
}

Rules:
- Use the legend text verbatim as each series "name" (the catalyst identity).
- Read the AXIS LABELS exactly as printed (do not guess the quantity).
- Read tick values; estimate each point's (x, y) against them.
- Only include series/points you can actually see. Never invent data.
- Lower "confidence" and explain in "notes" when unsure.

STACKED BAR CHARTS (segments piled on top of each other to a cumulative total,
e.g. product distributions B/T/EB/PX/MX/OX/TriMB):
- Each segment's value is its OWN height = (top boundary − bottom boundary),
  read from the baseline upward — NOT the cumulative position of its top edge.
- Work bottom-up: the bottom segment's value = its top boundary; each higher
  segment = (its top boundary) − (the segment top below it).
- The segment values within one bar should sum to the bar's total height.
- Represent each catalyst bar as a panel "series" whose name is the catalyst,
  with points {"x": "<product label>", "y": <segment height>}.
  (Do NOT report cumulative tops.)"""


class VisionChartExtractor:
    name = "vision"

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("CATALITMINE_VISION_MODEL",
                                             "claude-sonnet-4-5")
        self._client = None

    def _client_lazy(self):
        if self._client is None:
            from anthropic import Anthropic
            for var in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS",
                        "ANTHROPIC_BASE_URL"):
                os.environ.pop(var, None)
            key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            if not key:
                raise SystemExit("ANTHROPIC_API_KEY not set in environment/.env")
            self._client = Anthropic(api_key=key, base_url="https://api.anthropic.com")
        return self._client

    def extract(self, image_path: Path) -> ChartExtraction:
        media = mimetypes.guess_type(str(image_path))[0] or "image/png"
        data = base64.standard_b64encode(image_path.read_bytes()).decode()
        try:
            resp = self._client_lazy().messages.create(
                model=self.model, max_tokens=4000,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64",
                     "media_type": media, "data": data}},
                    {"type": "text", "text": _PROMPT}]}],
            )
            text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
        except Exception as e:
            return ChartExtraction(image=image_path.name, backend=self.name,
                                   model=self.model, error=f"api: {e}")
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if not m:
            return ChartExtraction(image=image_path.name, backend=self.name,
                                   model=self.model, error="no JSON in response")
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            return ChartExtraction(image=image_path.name, backend=self.name,
                                   model=self.model, error=f"json: {e}")
        return ChartExtraction(
            image=image_path.name, backend=self.name, model=self.model,
            panels=_parse_panels(obj),
            confidence=obj.get("confidence"), notes=obj.get("notes"))


# Placeholder for the reproducible backend built on feat/lineformer-standalone:
# class LineFormerChartExtractor:  name = "lineformer";  def extract(...): ...

def get_backend(name: str) -> ChartExtractor:
    if name == "vision":
        return VisionChartExtractor()
    raise SystemExit(f"unknown backend '{name}' (available: vision; "
                     "lineformer is on the feat/lineformer-standalone branch)")


# ── batch runner ────────────────────────────────────────────────────────────

def batch(extractor: ChartExtractor, images: list[Path], out_dir: Path) -> list[ChartExtraction]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for img in images:
        if not img.exists():
            print(f"  ✗ {img.name}: not found"); continue
        r = extractor.extract(img)
        (out_dir / f"{img.stem}.chart.json").write_text(
            json.dumps(r.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        if r.error:
            print(f"  ✗ {img.name}: {r.error}")
        else:
            sers = [s.name for p in r.panels for s in p.series]
            print(f"  ✓ {img.name}: {len(r.panels)} panel(s), {r.n_points} pts, "
                  f"conf={r.confidence} | series: {', '.join(sers)[:60]}")
        results.append(r)
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="Chart→data extraction (pluggable backends)")
    ap.add_argument("--image", help="single image")
    ap.add_argument("--dir", help="folder of images (.png/.jpg/.jpeg)")
    ap.add_argument("--backend", default="vision", help="vision (default)")
    ap.add_argument("--out", default=str(ROOT / "outputs" / "charts"))
    ap.add_argument("--min-size", type=int, default=120,
                    help="skip images whose width or height < this (logos/fragments)")
    args = ap.parse_args()

    imgs: list[Path] = []
    if args.image:
        imgs.append(Path(args.image))
    if args.dir:
        for ext in ("*.png", "*.jpg", "*.jpeg"):
            imgs += sorted(Path(args.dir).glob(ext))
    if not imgs:
        raise SystemExit("pass --image or --dir")

    # drop tiny fragments (Docling sometimes crops logos / sub-glyphs)
    if args.min_size:
        try:
            from PIL import Image
            kept = []
            for p in imgs:
                try:
                    w, h = Image.open(p).size
                    if w >= args.min_size and h >= args.min_size:
                        kept.append(p)
                except Exception:
                    kept.append(p)
            dropped = len(imgs) - len(kept)
            if dropped:
                print(f"(skipped {dropped} images < {args.min_size}px)")
            imgs = kept
        except ImportError:
            pass

    extractor = get_backend(args.backend)
    print(f"Backend: {args.backend}  | {len(imgs)} image(s)\n")
    results = batch(extractor, imgs, Path(args.out))
    ok = sum(1 for r in results if not r.error)
    pts = sum(r.n_points for r in results)
    print(f"\n{ok}/{len(results)} extracted, {pts} total points → {args.out}")


if __name__ == "__main__":
    main()

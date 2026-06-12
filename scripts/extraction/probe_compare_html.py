"""
probe_compare_html.py — 3-way comparison page for the LineFormer probe.

For every probe image: the ORIGINAL | LineFormer's trace overlay (+ its own
calibrated re-plot when its pipeline completed) | the deterministic CV
reader's re-plot. Human judges the geometry-layer verdict by eye.

  .venv-modal/bin/python3 ... NOT needed — runs on the repo venv:
  venv/bin/python3 scripts/extraction/probe_compare_html.py
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "extraction"))

PROBE = ROOT / "figures" / "lineformer_probe"
RESULTS = ROOT / "figures" / "lineformer_probe_results" / "output"
OUT_HTML = ROOT / "outputs" / "reports" / "lineformer_probe_compare.html"


def _b64_file(p: Path, max_w: int = 560) -> str | None:
    from PIL import Image
    if not p.exists():
        return None
    im = Image.open(p).convert("RGB")
    im.thumbnail((max_w, max_w))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


def _cv_replot(png: Path) -> tuple[str | None, str]:
    """Run the CV reader fresh and re-plot WITH the y-orientation fix."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import line_reader as lr
    try:
        res = lr.read_image(png)
    except Exception as e:
        return None, f"reader error: {e}"
    panels = res.get("panels", [])
    n = max(1, len(panels))
    fig, axes = plt.subplots(1, n, figsize=(4.4 * n, 3.4))
    if n == 1:
        axes = [axes]
    nseries = 0
    for ax, p in zip(axes, panels):
        for s in p["series"]:
            xs = [pt["x"] for pt in s["points"]]
            ys = [pt["y"] for pt in s["points"]]
            col = tuple(c / 255 for c in s.get("rgb", [0, 0, 0]))
            nseries += 1
            if s["kind"] == "scatter":
                ax.scatter(xs, ys, color=col, s=22, label=s["name"][:18])
            else:
                ax.plot(xs, ys, color=col, lw=1.6, label=s["name"][:18])
        calx, caly = p["x_axis"]["calibrated"], p["y_axis"]["calibrated"]
        if not caly:
            ax.invert_yaxis()        # pixel y grows downward — show true shape
        ax.set_title(f"{p['panel']}: {'calibrated' if calx and caly else 'pixel units'}",
                     fontsize=8)
        if p["series"]:
            ax.legend(fontsize=6)
        ax.tick_params(labelsize=7)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=105)
    plt.close(fig)
    buf.seek(0)
    return (base64.standard_b64encode(buf.read()).decode(),
            f"{nseries} series, {sum(1 for p in panels if p['x_axis']['calibrated'] and p['y_axis']['calibrated'])}/{len(panels)} panels calibrated")


def main() -> None:
    rows = []
    images = sorted(PROBE.glob("*.png"))
    for img in images:
        rd = RESULTS / img.name
        lf_overlay = _b64_file(rd / "lineformer" / "prediction.png")
        lf_plot = _b64_file(rd / "converted_datapoints" / "plot.png")
        coords = rd / "lineformer" / "coordinates.json"
        ntr = len(json.loads(coords.read_text())) if coords.exists() else 0
        cv_b64, cv_note = _cv_replot(img)
        cells = [f'<div><h4>original</h4><img src="data:image/png;base64,{_b64_file(img)}"></div>']
        if lf_overlay:
            cells.append(f'<div><h4>LineFormer traces ({ntr})</h4>'
                         f'<img src="data:image/png;base64,{lf_overlay}"></div>')
        else:
            cells.append(f'<div><h4>LineFormer traces ({ntr})</h4><p class=err>no overlay</p></div>')
        if lf_plot:
            cells.append(f'<div><h4>LineFormer pipeline re-plot (calibrated)</h4>'
                         f'<img src="data:image/png;base64,{lf_plot}"></div>')
        if cv_b64:
            cells.append(f'<div><h4>CV reader ({cv_note})</h4>'
                         f'<img src="data:image/png;base64,{cv_b64}"></div>')
        else:
            cells.append(f'<div><h4>CV reader</h4><p class=err>{cv_note}</p></div>')
        rows.append(f'<div class="fig"><h3>{img.name}</h3><div class="pair">{"".join(cells)}</div></div>')

    html = f"""<!doctype html><meta charset="utf-8">
<title>LineFormer probe — 3-way comparison</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:24px;background:#fafafa}}
 .fig{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px 16px;margin-bottom:24px}}
 .pair{{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start}}
 .pair img{{max-width:560px;border:1px solid #eee}}
 h4{{margin:4px 0}} .err{{color:#b44}}
</style>
<h1>LineFormer probe — 3-way comparison ({len(images)} images)</h1>
<p>Columns: published figure | LineFormer instance-segmentation traces |
(LineFormer pipeline's own calibrated re-plot, when its axis fusion completed: 7/30)
| deterministic CV reader re-plot (pixel-y flipped when uncalibrated).
Key questions: grayscale figures (catcom_2009, jcat_2015.01), crossing curves,
and whether trace counts match the printed series.</p>
{"".join(rows)}"""
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"→ {OUT_HTML}  ({len(images)} figures)")


if __name__ == "__main__":
    main()

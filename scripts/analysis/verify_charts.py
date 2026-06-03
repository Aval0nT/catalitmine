"""
verify_charts.py — human-verification view: source figure vs extracted data.

Builds a self-contained HTML page that places each figure image next to exactly
what was extracted from it (per panel: x/y axis labels, each series = catalyst,
all points). Open it in a browser and check, panel by panel, whether the
extraction matches the figure — BEFORE any normalisation is built on top.

Deliberately does no interpretation: it shows axis labels verbatim and keeps
each metric separate (no "performance" aggregation). Conversion, selectivity,
and yield are distinct quantities and are never merged.

  python3 scripts/analysis/verify_charts.py \
        --charts outputs/charts --figures figures/charts_test
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def find_image(name: str, fig_dirs: list[Path]) -> Path | None:
    for d in fig_dirs:
        p = d / name
        if p.exists():
            return p
    for d in fig_dirs:
        if d.exists():
            hits = list(d.glob(name)) or list(d.glob(Path(name).stem + ".*"))
            if hits:
                return hits[0]
    return None


def img_data_uri(p: Path) -> str:
    media = mimetypes.guess_type(str(p))[0] or "image/png"
    return f"data:{media};base64,{base64.standard_b64encode(p.read_bytes()).decode()}"


def panel_html(panel: dict) -> str:
    xa, ya = panel.get("x_axis") or {}, panel.get("y_axis") or {}
    rows = []
    for s in panel.get("series", []):
        pts = ", ".join(f"({pt.get('x')}, {pt.get('y')})" for pt in s.get("points", []))
        rows.append(
            f"<tr><td class='cat'>{html.escape(str(s.get('name','?')))}</td>"
            f"<td>{html.escape(pts)}</td></tr>")
    return f"""
      <div class="panel">
        <div class="axes">
          <b>panel {html.escape(str(panel.get('panel')))}</b>
          &nbsp;|&nbsp; type: {html.escape(str(panel.get('chart_type')))}<br>
          <b>x-axis:</b> {html.escape(str(xa.get('label')))} [{html.escape(str(xa.get('unit')))}]
          &nbsp;&nbsp; <b>y-axis:</b> {html.escape(str(ya.get('label')))} [{html.escape(str(ya.get('unit')))}]
        </div>
        <table><tr><th>series (= catalyst)</th><th>points (x, y)</th></tr>
        {''.join(rows)}</table>
      </div>"""


def build(charts_dir: Path, fig_dirs: list[Path]) -> str:
    blocks = []
    for jf in sorted(charts_dir.glob("*.chart.json")):
        ce = json.loads(jf.read_text(encoding="utf-8"))
        img = find_image(ce.get("image", ""), fig_dirs)
        img_html = (f"<img src='{img_data_uri(img)}'>" if img
                    else "<i>image not found</i>")
        if ce.get("error"):
            body = f"<p class='err'>extraction error: {html.escape(ce['error'])}</p>"
        else:
            body = (f"<p>confidence: <b>{html.escape(str(ce.get('confidence')))}</b>"
                    + (f" &nbsp;|&nbsp; notes: {html.escape(str(ce.get('notes')))}"
                       if ce.get('notes') else "") + "</p>"
                    + "".join(panel_html(p) for p in ce.get("panels", [])))
        blocks.append(f"""
        <section>
          <h2>{html.escape(ce.get('image',''))}</h2>
          <div class="row">
            <div class="fig">{img_html}</div>
            <div class="data">{body}</div>
          </div>
        </section>""")
    return f"""<!doctype html><html><head><meta charset="utf-8">
    <title>Chart extraction — verification</title>
    <style>
      body{{font:14px/1.5 -apple-system,sans-serif;margin:24px;color:#222}}
      h1{{font-size:20px}} h2{{font-size:15px;color:#0a58ca;margin:0 0 8px}}
      section{{border-top:2px solid #eee;padding:16px 0}}
      .row{{display:flex;gap:20px;align-items:flex-start}}
      .fig{{flex:0 0 46%}} .fig img{{max-width:100%;border:1px solid #ccc}}
      .data{{flex:1}}
      .panel{{margin:10px 0;padding:8px;background:#f7f9fc;border-radius:6px}}
      .axes{{margin-bottom:6px}}
      table{{border-collapse:collapse;width:100%;font-size:13px}}
      th,td{{border:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:top}}
      .cat{{font-weight:600;white-space:nowrap}}
      .err{{color:#b00}}
      .hint{{background:#fff3cd;padding:10px;border-radius:6px}}
    </style></head><body>
    <h1>Chart extraction — human verification</h1>
    <div class="hint">For each figure, check: (1) are the <b>axis labels</b> read
    correctly? (2) is each <b>series mapped to the right catalyst</b>? (3) are the
    <b>points</b> close to the figure? Note metrics are kept separate — conversion,
    selectivity, yield are distinct (yield = conversion × selectivity), never merged.</div>
    {''.join(blocks)}
    </body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="HTML verification: figure vs extraction")
    ap.add_argument("--charts", default=str(ROOT / "outputs" / "charts"))
    ap.add_argument("--figures", nargs="*",
                    default=[str(ROOT / "figures" / "charts_test"),
                             str(ROOT / "figures" / "charts")])
    ap.add_argument("--out", default=str(ROOT / "outputs" / "reports"
                                         / f"chart_verification_{date.today().isoformat()}.html"))
    args = ap.parse_args()
    fig_dirs = [Path(d) for d in args.figures]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(Path(args.charts), fig_dirs), encoding="utf-8")
    print(f"verification page → {out}")
    print("Open it in a browser, compare each figure with the extracted data,")
    print("and tell me what's wrong. No normalisation until you've confirmed.")


if __name__ == "__main__":
    main()

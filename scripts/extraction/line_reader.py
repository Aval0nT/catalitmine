"""
line_reader.py — deterministic CV reader for line/scatter charts (no model, no API).

Reads catalysis activity plots by pixels, completing the model-free figure
track started by bar_reader.py:

  1. AXES      — locate the plot box (dark low-saturation lines), find tick
                 marks, OCR the tick labels (Tesseract) and fit a linear
                 pixel→value calibration per axis.
  2. SERIES    — saturated-colour clustering inside the plot box gives the
                 series palette; the legend sample next to each colour is
                 OCR'd for the series name (catalyst identity).
  3. POINTS    — per colour: marker centroids (scatter) or per-column trace
                 (line), projected through the calibration into data space.

Output is chart_extractor-compatible JSON (panels/series/points + confidence
+ notes), so build_structure_activity.py and the verification HTML consume it
exactly like the vision backend's output.

  python3 scripts/extraction/line_reader.py read  --image fig.png [--debug]
  python3 scripts/extraction/line_reader.py batch --limit 20      # scope-driven
  python3 scripts/extraction/line_reader.py html                  # verify page

Requires the `tesseract` binary (brew install tesseract / apt install
tesseract-ocr) and pytesseract.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
ALL = ROOT / "figures" / "all_charts"
SCOPE = ROOT / "outputs" / "reports" / "figure_scope.jsonl"
OUT = ROOT / "outputs" / "charts"
DEBUG_DIR = ROOT / "figures" / "line_debug"
HTML_OUT = ROOT / "outputs" / "reports" / "line_reader_verify.html"

# ── shared pixel masks (same definitions as bar_reader) ─────────────────────

def axis_mask(arr: np.ndarray) -> np.ndarray:
    """Dark AND low-saturation pixels: axis lines, ticks, text — not data."""
    f = arr.astype(int)
    gray = f.mean(axis=2)
    sat = f.max(2) - f.min(2)
    return (gray < 110) & (sat < 45)


def line_mask(arr: np.ndarray) -> np.ndarray:
    """Looser mask for FRAME/TICK detection only: some journals draw axes in
    light gray (~160) that the strict text mask never sees. Still excludes
    saturated data colours."""
    f = arr.astype(int)
    gray = f.mean(axis=2)
    sat = f.max(2) - f.min(2)
    return (gray < 175) & (sat < 45)


def color_mask(arr: np.ndarray, rgb: tuple, tol: int = 60) -> np.ndarray:
    f = arr.astype(int)
    d = ((f[:, :, 0] - rgb[0]) ** 2 + (f[:, :, 1] - rgb[1]) ** 2
         + (f[:, :, 2] - rgb[2]) ** 2)
    return d < tol ** 2


# ── panel splitting (white-gutter projection) ────────────────────────────────

def split_panels(arr: np.ndarray, min_panel: int = 220):
    """Split a multi-panel figure on wide near-white gutters. Returns a list of
    (sub_array, (x_off, y_off)). Conservative: only splits when both halves
    are big enough to be plots; recurses once per direction."""
    h, w, _ = arr.shape
    nonwhite = (arr.astype(int).sum(axis=2) < 690)  # anything not near-white

    def gutters(profile, span, min_gut=14):
        """A gutter is a NEAR-white run ≥ min_gut px, or an EXACTLY-blank run
        ≥ 4 px — journals pack subplots with 3–5 px pixel-perfect gutters."""
        runs, i = [], 0
        while i < len(profile):
            if profile[i] <= span * 0.004:
                j = i
                while j < len(profile) and profile[j] <= span * 0.004:
                    j += 1
                width = j - i
                if width >= min_gut or \
                   (width >= 4 and all(profile[t] == 0 for t in range(i, j))):
                    runs.append((i + j) // 2)
                i = j
            else:
                i += 1
        return [g for g in runs if min_panel < g < len(profile) - min_panel]

    col_gut = gutters(nonwhite.sum(axis=0), h)
    if col_gut:
        g = col_gut[len(col_gut) // 2]
        left = split_panels(arr[:, :g], min_panel)
        right = [(a, (x + g, y)) for a, (x, y) in split_panels(arr[:, g:], min_panel)]
        return left + right
    row_gut = gutters(nonwhite.sum(axis=1), w)
    if row_gut:
        g = row_gut[len(row_gut) // 2]
        top = split_panels(arr[:g], min_panel)
        bot = [(a, (x, y + g)) for a, (x, y) in split_panels(arr[g:], min_panel)]
        return top + bot
    return [(arr, (0, 0))]


# ── plot-box detection ───────────────────────────────────────────────────────

def find_plot_box(arr: np.ndarray):
    """(x0, y0, x1, y1, has_axes) of the plot area. has_axes=False means no
    drawn axis line was found on ANY edge — almost certainly not a data chart
    (scheme, micrograph, cartoon) and the caller should refuse to read it."""
    h, w, _ = arr.shape
    m = line_mask(arr)
    col = m.sum(axis=0)
    row = m.sum(axis=1)
    found = 0
    # y-axis: leftmost of the near-longest vertical runs in the left 45 %
    # (with gridlines visible under the loose mask, argmax alone could pick
    # an interior gridline — prefer the leftmost equally-long line)
    left = col[: int(w * 0.45)]
    if left.size and left.max() > 0.15 * h:
        near = np.where(left >= 0.92 * left.max())[0]
        x0 = int(near[0])
        found += 1
    else:
        x0 = int(w * 0.1)
    # baseline: lowest long row in the bottom 60 %
    cand = [r for r in range(int(h * 0.4), h) if row[r] > 0.35 * w]
    if cand:
        y1 = max(cand)
        found += 1
    else:
        y1 = int(h * 0.9)
    # top: highest long row above the baseline (frame) else small margin
    cand_t = [r for r in range(0, int(h * 0.6)) if row[r] > 0.35 * w]
    y0 = min(cand_t) if cand_t else int(h * 0.04)
    if y0 >= y1:
        y0 = int(h * 0.04)
    # right edge: longest vertical run in the right 30 %, else margin
    rstart = int(w * 0.7)
    right = col[rstart:]
    x1 = rstart + int(np.argmax(right)) if right.size and right.max() > 0.3 * h \
        else int(w * 0.97)
    if x1 <= x0 + 50:
        x1 = int(w * 0.97)
    return x0, y0, x1, y1, found > 0


def find_ticks(arr: np.ndarray, box, axis: str) -> list[int]:
    """Pixel positions of tick MARKS: short stubs just OUTSIDE the axis line;
    when none exist there, fall back to INWARD-pointing stubs just inside the
    frame (matplotlib/LaTeX default). Threshold is 2 px of ink — real stubs
    can be as short as 2 px."""
    x0, y0, x1, y1 = box
    m = line_mask(arr)

    def scan(strip, lo, hi, transpose=False):
        hits = strip.sum(axis=0 if not transpose else 1)
        idx = [v for v in range(lo, min(hi + 1, len(hits))) if hits[v] >= 2]
        cand = []
        for v in idx:
            if not cand or v - cand[-1][0] > 5:
                cand.append((v, int(hits[v])))
            elif hits[v] > cand[-1][1]:
                cand[-1] = (v, int(hits[v]))
        if not cand:
            return []
        # MAJOR ticks only: minor ticks (which surface at higher render
        # scales) have visibly shorter stubs — keep ticks near the max ink
        top = max(n for _, n in cand)
        ticks = [v for v, n in cand if n >= max(2, 0.7 * top)]
        return ticks

    if axis == "x":
        ticks = scan(m[y1 + 2: y1 + 8, :], x0, x1)
        if len(ticks) < 2:
            ticks = scan(m[max(0, y1 - 8): y1 - 1, :], x0 + 4, x1 - 1)
    else:
        ticks = scan(m[:, max(0, x0 - 7): x0 - 1], y0, y1, transpose=True)
        if len(ticks) < 2:
            ticks = scan(m[:, x0 + 2: x0 + 8], y0 + 4, y1 - 1, transpose=True)
    return ticks


# ── tick-label OCR (Tesseract) ───────────────────────────────────────────────

_NUM = re.compile(r"^-?\d+\.?\d*$")

def _ocr_number(arr_crop: np.ndarray):
    """OCR a small crop expected to hold ONE tick label; float or None.

    The crop is masked to DARK ink first — tick labels are always printed
    dark, while coloured decorations, gridlines, and data ink near the axis
    otherwise read as phantom digits. Stub dashes are stripped on both sides,
    so negative tick labels are not supported (none exist in this corpus)."""
    import pytesseract
    if arr_crop.size == 0:
        return None
    dark = axis_mask(arr_crop)
    if dark.sum() < 6:
        return None
    clean = np.where(dark[..., None], arr_crop, np.uint8(255))
    img = Image.fromarray(clean)
    img = img.resize((img.width * 3, img.height * 3), Image.LANCZOS)
    txt = pytesseract.image_to_string(
        img, config="--psm 7 -c tessedit_char_whitelist=0123456789.-").strip()
    t = txt.replace(" ", "").replace("..", ".").strip(".-")
    if _NUM.match(t):
        try:
            v = float(t)
            if abs(v) < 1e5:        # tick labels are small numbers
                return v
        except ValueError:
            pass
    return None


def calibrate_axis(arr: np.ndarray, box, axis: str):
    """Fit value = a·px + b by OCR-ing a small window around EACH tick mark
    (single-label crops are far more reliable than whole-strip OCR).

    Returns (a, b, n_matched, label_positions) or None when no trustworthy
    calibration exists — the panel is then reported in pixel units instead of
    silently guessed."""
    x0, y0, x1, y1 = box
    h, w, _ = arr.shape
    ticks = find_ticks(arr, box, axis)
    # OCR window must stay narrower than the tick spacing, or the neighbour's
    # label bleeds in ("5" + "10" reads as "51")
    if len(ticks) >= 2:
        gap = int(np.median(np.diff(ticks)))
        half = max(10, min(30, int(gap * 0.45)))
    else:
        half = 24
    # locate the x-label TEXT BAND below the baseline instead of assuming a
    # fixed offset — long tick stubs (and the 2x panel upscale) push labels
    # well below y1+36
    if axis == "x":
        # profile only the PLOT's column range — decorations beside the plot
        # would bridge the label row into whatever sits below it
        prof = axis_mask(arr)[y1 + 3: min(h, y1 + 90), x0: x1].sum(axis=1)
        rows = np.where(prof > 0.01 * (x1 - x0))[0]
        # group into runs; the LABEL run is the first one at least a text-line
        # tall (≥6 px) — thinner first runs are tick-stub remnants
        runs = []
        for r in rows:
            if runs and r - runs[-1][1] <= 3:
                runs[-1][1] = int(r)
            else:
                runs.append([int(r), int(r)])
        label_run = next((rn for rn in runs if rn[1] - rn[0] >= 5), None)
        if label_run:
            band0 = y1 + 3 + label_run[0]
            # one text line only — labels are never taller than ~40 px here
            band1 = min(h, max(y1 + 3 + label_run[1] + 3, band0 + 12),
                        band0 + 40)
        else:
            band0, band1 = y1 + 4, min(h, y1 + 36)
    pairs = []
    for t in ticks:
        if axis == "x":
            crop = arr[band0: band1, max(0, t - half): min(w, t + half)]
        else:
            # narrow first, widen on failure: wide crops can swallow figure
            # decorations left of the labels, narrow ones can clip "100";
            # the tick stub riding in is handled by the trailing-dash strip
            v = None
            for width in (62, 84):
                crop = arr[max(0, t - min(half, 15)): min(h, t + min(half, 15)),
                           max(0, x0 - width): max(1, x0 - 2)]
                v = _ocr_number(crop)
                if v is not None:
                    break
            if v is not None:
                pairs.append((v, t))
            continue
        v = _ocr_number(crop)
        if v is not None:
            pairs.append((v, t))

    used_fallback = False
    if len(pairs) < 2:
        used_fallback = True
        # frames without tick stubs: OCR the whole strip and use the label
        # centres themselves as positions
        import pytesseract
        if axis == "x":
            strip = arr[band0: band1, :]
            off = 0
        else:
            off = max(0, x0 - 84)
            strip = arr[:, off: max(1, x0 - 2)]
        if strip.size:
            img = Image.fromarray(strip)
            img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
            data = pytesseract.image_to_data(
                img, config="--psm 6 -c tessedit_char_whitelist=0123456789.-",
                output_type=pytesseract.Output.DICT)
            for i, txt in enumerate(data["text"]):
                t2 = txt.strip().replace("..", ".").rstrip(".-")
                if _NUM.match(t2) and abs(float(t2)) < 1e5:
                    if axis == "x":
                        pos = (data["left"][i] + data["width"][i] / 2) / 2
                    else:
                        pos = (data["top"][i] + data["height"][i] / 2) / 2
                    pairs.append((float(t2), pos))

    # dedupe: a label read at two neighbouring ticks keeps the first
    seen, uniq = set(), []
    for v, p in sorted(pairs, key=lambda vp: vp[1]):
        if all(abs(p - q) > 6 for q in seen):
            uniq.append((v, p)); seen.add(p)
    pairs = uniq
    # the strip fallback has no tick-position crosscheck: a 2-point fit from
    # two misread labels once produced garbage with calibrated=true — demand 3
    if len(pairs) < (3 if used_fallback else 2):
        return None

    vals = np.array([v for v, _ in pairs], float)
    pxs = np.array([p for _, p in pairs], float)
    span = (x1 - x0) if axis == "x" else (y1 - y0)
    order = np.argsort(pxs)
    vals, pxs = vals[order], pxs[order]

    fit = _fit_ticks(vals, pxs, span)
    if fit is None and len(pairs) >= 4:
        # one garbled label ("10" read as "40") can be monotonic yet break the
        # uniform-grid slope test: retry with each single point left out
        for i in range(len(pairs)):
            keep = np.ones(len(pairs), bool); keep[i] = False
            fit = _fit_ticks(vals[keep], pxs[keep], span)
            if fit is not None:
                vals, pxs = vals[keep], pxs[keep]
                break
    if fit is None:
        return None
    a, b = fit
    return float(a), float(b), int(len(vals)), [int(p) for p in pxs]


def _fit_ticks(vals: np.ndarray, pxs: np.ndarray, span: float):
    """Linear fit with the trust checks: pixel spread, distinct monotonic
    values, uniform-grid slope consistency, sane magnitudes."""
    if len(vals) < 2 or len(set(vals)) < 2:
        return None
    if (pxs.max() - pxs.min()) < 0.18 * span:
        return None
    if not (all(np.diff(vals) > 0) or all(np.diff(vals) < 0)):
        return None
    a, b = np.polyfit(pxs, vals, 1)
    if len(pxs) >= 3:
        gaps = np.diff(vals) / np.diff(pxs)
        ratio = abs(gaps).max() / max(abs(gaps).min(), 1e-12)
        if gaps.min() * gaps.max() <= 0 or ratio > 1.6:
            return None
    if abs(a) * span > 1e6 or abs(b) > 1e6:
        return None
    return float(a), float(b)


# ── series colours + legend names ────────────────────────────────────────────

def series_colors(arr: np.ndarray, box, k: int = 6):
    """Dominant saturated colours INSIDE the plot box (the data palette).
    Each kept colour is the MEAN of its pixels (not a quantization-bin centre),
    and near-duplicates — a solid line and its lighter dashed twin — merge."""
    x0, y0, x1, y1 = box
    inner = arr[y0 + 3: y1 - 2, x0 + 3: x1 - 2]
    flat = inner.reshape(-1, 3).astype(int)
    sat = flat.max(1) - flat.min(1)
    keep = flat[(sat > 60) & (flat.max(1) > 70)]
    if keep.size == 0:
        return []
    q = np.minimum((keep // 36) * 36 + 18, 255)
    colors, inv, counts = np.unique(q, axis=0, return_counts=True,
                                    return_inverse=True)
    order = np.argsort(-counts)
    out = []
    for i in order:
        n = int(counts[i])
        if n < 40:
            break
        rgb = tuple(int(round(v)) for v in keep[inv == i].mean(axis=0))
        merged = False
        for j, (o, on) in enumerate(out):
            # same HUE = same series (a solid line and its lighter dashed
            # twin differ a lot in RGB but barely in hue)
            if _hue_dist(rgb, o) < 22 or \
               sum((rgb[c] - o[c]) ** 2 for c in range(3)) <= 88 ** 2:
                tot = on + n
                out[j] = (tuple(int(round((o[c] * on + rgb[c] * n) / tot))
                                for c in range(3)), tot)
                merged = True
                break
        if not merged:
            out.append((rgb, n))
        if len(out) >= k:
            break
    return out


def _hue_dist(a, b) -> float:
    import colorsys
    ha = colorsys.rgb_to_hsv(*[c / 255 for c in a])[0] * 360
    hb = colorsys.rgb_to_hsv(*[c / 255 for c in b])[0] * 360
    d = abs(ha - hb)
    return min(d, 360 - d)


_HUE_NAMES = [(0, "red"), (20, "orange"), (45, "yellow"), (85, "green"),
              (160, "cyan"), (210, "blue"), (270, "purple"), (320, "magenta"),
              (345, "red")]

def color_name(rgb) -> str:
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*[c / 255 for c in rgb])
    deg = h * 360
    for lim, name in _HUE_NAMES:
        if deg <= lim:
            return name
    return "red"


def legend_names(arr: np.ndarray, colors: list, box) -> dict:
    """For each series colour, find a LEGEND SAMPLE (a small isolated component
    of that colour) and OCR the text to its right. Data clusters are large or
    numerous; the legend sample is the small one with dark text beside it."""
    import pytesseract
    h, w, _ = arr.shape
    # legend labels may themselves be coloured ("TNU-9" printed in red), so
    # the text-presence test uses any NON-WHITE ink, not just dark pixels
    text_px = (arr.astype(int).sum(axis=2) < 660)
    names = {}
    for rgb, _ in colors:
        mask = color_mask(arr, rgb)
        lab, n = ndimage.label(mask)
        if not n:
            continue
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        objs = ndimage.find_objects(lab)
        cands = []
        for i, sl in enumerate(objs):
            if sl is None or sizes[i] < 12:
                continue
            bh = sl[0].stop - sl[0].start
            bw = sl[1].stop - sl[1].start
            if bh > 26 or bw > 70:               # too big to be a legend sample
                continue
            cy = (sl[0].start + sl[0].stop) // 2
            rx0, rx1 = sl[1].stop + 4, min(w, sl[1].stop + 190)
            band = text_px[max(0, cy - 11): cy + 11, rx0: rx1]
            density = band.mean() if band.size else 0
            if density > 0.04:                   # dark text sits to the right
                cands.append((density, cy, rx0, rx1))
        if not cands:
            continue
        cands.sort(reverse=True)
        _, cy, rx0, rx1 = cands[0]
        crop = Image.fromarray(arr[max(0, cy - 13): cy + 13, rx0: rx1])
        crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
        txt = pytesseract.image_to_string(crop, config="--psm 7").strip()
        label = _clean_label(txt)
        if label:
            names[rgb] = label
    return names


def _clean_label(txt: str) -> str | None:
    """Strip the marker glyphs OCR drags along ('% ke ZSM-11' → 'ZSM-11'):
    keep only tokens that look like catalyst identifiers — containing a digit,
    a slash, or ≥3 letters with an uppercase start."""
    tokens = re.findall(r"[A-Za-z0-9][\w\-/.%()]*", txt)
    kept = [t for t in tokens
            if any(c.isdigit() for c in t) or "/" in t
            or (len(t) >= 3 and t[0].isupper())]
    label = " ".join(kept).strip()
    return label[:40] if len(label) >= 2 else None


# ── point extraction ─────────────────────────────────────────────────────────

def extract_points(arr: np.ndarray, box, rgb, max_pts: int = 30):
    """Pixel-space data points for one colour: marker centroids when the mask
    decomposes into discrete blobs, else a per-column line trace."""
    x0, y0, x1, y1 = box
    mask = color_mask(arr, rgb)
    mask[: y0 + 2, :] = False
    mask[y1 - 1:, :] = False
    mask[:, : x0 + 2] = False
    mask[:, x1 - 1:] = False
    if mask.sum() < 25:
        return [], "none"
    lab, n = ndimage.label(mask)
    if n == 0:
        return [], "none"
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    big = sizes[sizes >= 9]
    # scatter: a handful of similar-sized compact blobs
    if 2 <= len(big) <= 60 and (np.median(big) > 0) \
       and (big.max() / max(np.median(big), 1) < 12):
        cents = ndimage.center_of_mass(mask, lab,
                                       [i + 1 for i in range(n) if sizes[i] >= 9])
        pts = sorted((float(cx), float(cy)) for cy, cx in cents)
        return pts, "scatter"
    # line: per-column median row of the mask
    cols = np.where(mask.any(axis=0))[0]
    if cols.size < 8:
        return [], "none"
    pts = []
    step = max(1, (cols[-1] - cols[0]) // max_pts)
    for cx in range(cols[0], cols[-1] + 1, step):
        rows = np.where(mask[:, cx])[0]
        if rows.size:
            pts.append((float(cx), float(np.median(rows))))
    return pts, "line"


# ── panel → structured result ────────────────────────────────────────────────

def read_panel(arr: np.ndarray, panel_tag: str) -> dict:
    notes = []
    *box, has_axes = find_plot_box(arr)
    box = tuple(box)
    if not has_axes:
        # no drawn axis line on any edge: a scheme / micrograph / cartoon —
        # refuse to invent data from it
        return {"panel": panel_tag, "chart_type": None,
                "x_axis": {"label": None, "unit": None, "calibrated": False,
                           "ticks_used": 0},
                "y_axis": {"label": None, "unit": None, "calibrated": False,
                           "ticks_used": 0},
                "series": [], "confidence": "low",
                "notes": "no axis lines found — likely not a data chart",
                "_box": list(box)}
    cal_x = calibrate_axis(arr, box, "x")
    cal_y = calibrate_axis(arr, box, "y")
    if cal_x is None:
        notes.append("x-axis not calibrated (<2 tick labels OCR'd)")
    if cal_y is None:
        notes.append("y-axis not calibrated (<2 tick labels OCR'd)")
    colors = series_colors(arr, box)
    names = legend_names(arr, colors, box) if colors else {}
    series = []
    for rgb, _ in colors:
        pts_px, kind = extract_points(arr, box, rgb)
        if not pts_px:
            continue
        name = names.get(rgb)
        if not name:
            name = color_name(rgb)
            notes.append(f"no legend text for {name} series — colour name used")
        pts = []
        for px, py in pts_px:
            x = round(cal_x[0] * px + cal_x[1], 3) if cal_x else round(px, 1)
            y = round(cal_y[0] * py + cal_y[1], 3) if cal_y else round(py, 1)
            pts.append({"x": x, "y": y})
        series.append({"name": name, "kind": kind, "rgb": list(rgb),
                       "points": pts})
    if not series:
        notes.append("no coloured series found inside the plot box")
    conf = "high"
    if cal_x is None or cal_y is None or not series:
        conf = "low"
    elif any(s["name"] in {n for _, n in _HUE_NAMES} for s in series) \
            or (cal_x and cal_x[2] < 3) or (cal_y and cal_y[2] < 3):
        conf = "medium"
    return {
        "panel": panel_tag, "chart_type": series[0]["kind"] if series else None,
        "x_axis": {"label": None, "unit": None,
                   "calibrated": cal_x is not None,
                   "ticks_used": cal_x[2] if cal_x else 0},
        "y_axis": {"label": None, "unit": None,
                   "calibrated": cal_y is not None,
                   "ticks_used": cal_y[2] if cal_y else 0},
        "series": series, "confidence": conf,
        "notes": "; ".join(notes) if notes else None,
        "_box": list(box),
    }


def read_image(path: Path, debug: bool = False) -> dict:
    arr = np.asarray(Image.open(path).convert("RGB"))
    panels = split_panels(arr)
    out_panels = []
    for i, (sub, (ox, oy)) in enumerate(panels):
        tag = chr(ord("a") + i) if len(panels) > 1 else "a"
        # tick labels in small panels are below Tesseract's glyph size —
        # upscale the whole panel before reading (geometry scales with it)
        if sub.shape[0] < 430 or sub.shape[1] < 430:
            im2 = Image.fromarray(sub)
            im2 = im2.resize((im2.width * 2, im2.height * 2), Image.LANCZOS)
            sub = np.asarray(im2)
        p = read_panel(sub, tag)
        p["_offset"] = [ox, oy]
        out_panels.append(p)
        if debug:
            _save_debug(sub, p, f"{path.stem}_{tag}")
    confs = [p["confidence"] for p in out_panels]
    overall = ("high" if all(c == "high" for c in confs) else
               "low" if all(c == "low" for c in confs) else "medium")
    return {
        "image": path.name, "backend": "cv-line", "model": None,
        "panels": out_panels, "confidence": overall,
        "notes": None,
        "error": None if any(p["series"] for p in out_panels)
                 else "no series extracted",
    }


def _save_debug(arr, panel, stem):
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    im = Image.fromarray(arr).convert("RGB")
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = panel["_box"]
    d.rectangle([x0, y0, x1, y1], outline=(255, 0, 255))
    im.save(DEBUG_DIR / f"{stem}_debug.png")


# ── verification HTML (original | re-plot | numbers) ────────────────────────

def _b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


def replot(result: dict, src: Image.Image) -> Image.Image:
    """Re-draw the EXTRACTED data with matplotlib so the eye can compare the
    shape against the original at a glance."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    panels = [p for p in result["panels"]]
    n = max(1, len(panels))
    fig, axes = plt.subplots(1, n, figsize=(4.6 * n, 3.6))
    if n == 1:
        axes = [axes]
    for ax, p in zip(axes, panels):
        for s in p["series"]:
            xs = [pt["x"] for pt in s["points"]]
            ys = [pt["y"] for pt in s["points"]]
            col = tuple(c / 255 for c in s.get("rgb", [0, 0, 0]))
            if s["kind"] == "scatter":
                ax.scatter(xs, ys, color=col, s=28, label=s["name"][:22])
            else:
                ax.plot(xs, ys, color=col, lw=1.8, label=s["name"][:22])
        cal = "calibrated" if p["x_axis"]["calibrated"] and p["y_axis"]["calibrated"] \
              else "PIXEL UNITS (uncalibrated)"
        ax.set_title(f"panel {p['panel']} — {cal}", fontsize=9)
        if p["series"]:
            ax.legend(fontsize=7)
        ax.tick_params(labelsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def build_html(results: list[tuple[Path, dict, str]], out: Path) -> None:
    rows = []
    for img_path, res, caption in results:
        src = Image.open(img_path).convert("RGB")
        src.thumbnail((620, 620))
        try:
            rp = replot(res, src)
            rp.thumbnail((620, 620))
            rp_b64 = _b64(rp)
        except Exception as e:
            rp_b64 = None
        tables = []
        for p in res["panels"]:
            for s in p["series"]:
                pts = ", ".join(f"({pt['x']:g}, {pt['y']:g})"
                                for pt in s["points"][:8])
                more = f" … +{len(s['points']) - 8}" if len(s["points"]) > 8 else ""
                tables.append(
                    f"<tr><td>{p['panel']}</td><td>{s['name']}</td>"
                    f"<td>{s['kind']}</td><td>{len(s['points'])}</td>"
                    f"<td class=pts>{pts}{more}</td></tr>")
        notes = "; ".join(filter(None, (p.get("notes") for p in res["panels"])))
        conf = res["confidence"]
        rows.append(f"""
<div class="fig {conf}">
  <h3>{img_path.name} <span class="conf {conf}">{conf}</span></h3>
  <p class="cap">{caption or ''}</p>
  <div class="pair">
    <div><h4>original</h4><img src="data:image/png;base64,{_b64(src)}"></div>
    <div><h4>re-plotted from extracted data</h4>{
        f'<img src="data:image/png;base64,{rp_b64}">' if rp_b64
        else '<p class=err>re-plot failed</p>'}</div>
  </div>
  <table><tr><th>panel</th><th>series</th><th>kind</th><th>#pts</th><th>points (x, y)</th></tr>
  {''.join(tables) or '<tr><td colspan=5>no series extracted</td></tr>'}</table>
  <p class="notes">{notes or ''}</p>
</div>""")
    html = f"""<!doctype html><meta charset="utf-8">
<title>line_reader verification</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:24px;background:#fafafa}}
 .fig{{background:#fff;border:1px solid #ddd;border-radius:8px;
      padding:14px 18px;margin-bottom:26px}}
 .fig.low{{border-color:#e08585}}
 .pair{{display:flex;gap:18px;flex-wrap:wrap}}
 .pair img{{max-width:620px;border:1px solid #eee}}
 .conf{{font-size:.7em;padding:2px 8px;border-radius:10px;color:#fff}}
 .conf.high{{background:#2e9e44}} .conf.medium{{background:#d9962e}}
 .conf.low{{background:#cc4444}}
 .cap{{color:#555;font-size:.85em}}
 table{{border-collapse:collapse;margin-top:10px;font-size:.8em}}
 td,th{{border:1px solid #ccc;padding:3px 8px;text-align:left}}
 .pts{{font-family:ui-monospace,monospace;font-size:.92em}}
 .notes{{color:#a66;font-size:.8em}}
</style>
<h1>line_reader — verification ({len(results)} figures)</h1>
<p>Left: the published figure. Right: the SAME data as extracted by the
deterministic reader, re-plotted. If the shapes match, the extraction is
faithful; confidence chips mark what to check first.</p>
{''.join(rows)}"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")


# ── CLI ──────────────────────────────────────────────────────────────────────

def _scope_rows(limit=None, shapes=("line/scatter",)):
    rows = [json.loads(l) for l in open(SCOPE, encoding="utf-8")]
    sel = [r for r in rows if r.get("shape") in shapes]
    return sel[:limit] if limit else sel


def main() -> None:
    ap = argparse.ArgumentParser(description="Deterministic line/scatter reader")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("read", help="read one image")
    rp.add_argument("--image", required=True)
    rp.add_argument("--debug", action="store_true")
    bp = sub.add_parser("batch", help="read the line/scatter scope subset")
    bp.add_argument("--limit", type=int, default=None)
    bp.add_argument("--skip-existing", action=argparse.BooleanOptionalAction,
                    default=True)
    hp = sub.add_parser("html", help="build the verification HTML")
    hp.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if args.cmd == "read":
        p = Path(args.image)
        res = read_image(p, debug=args.debug)
        for pan in res["panels"]:
            pan.pop("_box", None); pan.pop("_offset", None)
        print(json.dumps(res, indent=2)[:4000])
        return

    if args.cmd == "batch":
        OUT.mkdir(parents=True, exist_ok=True)
        sel = _scope_rows(args.limit)
        done = skipped = failed = 0
        for r in sel:
            slug = r["doi"].replace("/", "_")
            png = ALL / slug / r["figure"]
            if not png.exists():
                continue
            out = OUT / f"{png.stem}.cvline.json"
            if args.skip_existing and out.exists():
                try:
                    prev = json.loads(out.read_text(encoding="utf-8"))
                    if not prev.get("error"):
                        skipped += 1; continue
                except Exception:
                    pass
            try:
                res = read_image(png)
            except Exception as e:
                res = {"image": png.name, "backend": "cv-line", "panels": [],
                       "confidence": None, "error": f"reader: {e}"}
            for pan in res.get("panels", []):
                pan.pop("_box", None); pan.pop("_offset", None)
            out.write_text(json.dumps(res, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            ok = not res.get("error")
            done += ok; failed += (not ok)
            npts = sum(len(s["points"]) for p in res.get("panels", [])
                       for s in p["series"])
            print(f"  {'✓' if ok else '✗'} {png.stem[:52]:52s} "
                  f"{res.get('confidence') or '—':6s} {npts:3d}pts")
        print(f"\n{done} read, {failed} failed, {skipped} skipped → {OUT}")
        return

    if args.cmd == "html":
        caps = {}
        for r in _scope_rows():
            caps[r["figure"]] = r.get("caption", "")
        results = []
        for f in sorted(OUT.glob("*.cvline.json")):
            res = json.loads(f.read_text(encoding="utf-8"))
            stem = f.name.replace(".cvline.json", "")
            slug = stem.split("_fig")[0]
            png = ALL / slug / f"{stem}.png"
            if png.exists() and not res.get("error"):
                results.append((png, res, caps.get(png.name, "")))
        # best first: the reviewer sees the usable extractions before the tail
        def quality(item):
            _, res, _ = item
            ncal = sum(1 for p in res["panels"]
                       if p["x_axis"]["calibrated"] and p["y_axis"]["calibrated"])
            return (-(res["confidence"] == "medium"), -ncal)
        results.sort(key=quality)
        if args.limit:
            results = results[: args.limit]
        build_html(results, HTML_OUT)
        print(f"verification page → {HTML_OUT}  ({len(results)} figures)")


if __name__ == "__main__":
    main()

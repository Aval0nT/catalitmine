"""
bar_reader.py — deterministic CV reader for bar charts (Branch A, no PyTorch).

Stacked / grouped bar charts are where LLM vision is weakest (it misread benzene
as 32 % instead of ~10 %). This reads them by pixels: detect the plot axes,
calibrate y (pixel -> value), classify each bar column's pixels against the
legend colours, and measure segment heights as DIFFERENCES (bottom-up). Fully
deterministic and verifiable.

This first stage is INSPECTION: it loads an image, locates the plot axes and the
colour palette, and writes a debug overlay so we can ground the segmentation
design on real pixel coordinates (not eyeballing).

  python3 scripts/extraction/bar_reader.py inspect --image fig.png [--crop top|bottom]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "figures" / "bar_debug"


def load(path: Path, crop: str | None) -> np.ndarray:
    im = Image.open(path).convert("RGB")
    arr = np.asarray(im)
    h = arr.shape[0]
    if crop == "top":
        arr = arr[: h // 2]
    elif crop == "bottom":
        arr = arr[h // 2:]
    return arr


def axis_mask(arr: np.ndarray) -> np.ndarray:
    """Pixels that belong to AXIS lines/text: dark AND low-saturation (gray/black).
    Excludes the saturated bar colours that previously fooled the detector."""
    f = arr.astype(int)
    gray = f.mean(axis=2)
    sat = f.max(2) - f.min(2)
    return (gray < 100) & (sat < 45)


def find_axes(arr: np.ndarray):
    """y-axis = left column with the longest vertical gray run; baseline = lowest
    long horizontal gray row."""
    h, w, _ = arr.shape
    m = axis_mask(arr)
    col_cnt = m.sum(axis=0)
    row_cnt = m.sum(axis=1)
    # y-axis: in left 45%, the column whose gray run covers most of the height
    left = col_cnt[: int(w * 0.45)].copy()
    y_axis_x = int(np.argmax(left)) if left.size else 0
    # baseline: lowest row whose gray run spans most of the width
    thr = 0.35 * w
    cand = [r for r in range(int(h * 0.5), h) if row_cnt[r] > thr]
    baseline_y = max(cand) if cand else h - 1
    cand_top = [r for r in range(0, int(h * 0.6)) if row_cnt[r] > thr]
    top_y = min(cand_top) if cand_top else 0
    return y_axis_x, baseline_y, top_y


def find_yticks(arr: np.ndarray, y_axis_x: int):
    """Tick rows = short gray marks just LEFT of the axis line. Returns sorted
    pixel rows (top→bottom). Their even spacing calibrates the scale."""
    m = axis_mask(arr)
    x0 = max(0, y_axis_x - 6)
    strip = m[:, x0:y_axis_x]               # the few columns left of the axis
    rowhit = strip.sum(axis=1)
    rows = [r for r in range(len(rowhit)) if rowhit[r] >= max(1, (y_axis_x - x0) // 2)]
    # collapse consecutive rows into single ticks
    ticks = []
    for r in rows:
        if not ticks or r - ticks[-1] > 4:
            ticks.append(r)
    return ticks


def palette(arr: np.ndarray, k: int = 8):
    """Most common saturated colours (the bar/legend palette), quantized."""
    flat = arr.reshape(-1, 3).astype(int)
    r, g, b = flat[:, 0], flat[:, 1], flat[:, 2]
    mx, mn = flat.max(1), flat.min(1)
    sat = (mx - mn)
    bright = mx
    keep = flat[(sat > 60) & (bright > 80)]          # drop greys/white/black
    if keep.size == 0:
        return []
    q = (keep // 32) * 32 + 16                        # quantize to 8 levels/chan
    colors, counts = np.unique(q, axis=0, return_counts=True)
    order = np.argsort(-counts)
    return [(tuple(int(x) for x in colors[i]), int(counts[i]))
            for i in order[:k]]


def detect_bars(arr, y_axis_x, baseline_y):
    """Bar x-ranges = contiguous columns that have a saturated colour sitting ON
    the baseline (excludes floating legend swatches up top)."""
    f = arr.astype(int)
    sat = f.max(2) - f.min(2)
    bright = f.max(2)
    colored = (sat > 60) & (bright > 80)
    band = colored[baseline_y - 9: baseline_y - 1, :].sum(axis=0)  # sits on baseline
    band[: y_axis_x + 2] = 0
    on = band >= 4
    # close small gaps so a thin gridline/annotation inside one bar doesn't split
    # it into two (groups of separate bars are far apart, so this is safe)
    maxgap = 20
    on = on.astype(bool)
    i = 0
    n = len(on)
    while i < n:
        if not on[i]:
            j = i
            while j < n and not on[j]:
                j += 1
            if 0 < i and j < n and (j - i) <= maxgap:   # gap flanked by bars
                on[i:j] = True
            i = j
        else:
            i += 1
    bars, in_bar, start = [], False, 0
    for x in range(len(on)):
        if on[x] and not in_bar:
            in_bar, start = True, x
        elif not on[x] and in_bar:
            in_bar = False
            if x - start >= 5:
                bars.append((start, x))
    if in_bar and len(on) - start >= 5:
        bars.append((start, len(on)))
    return bars


def classify(px, legend):
    """Nearest legend colour within tolerance, else None (background)."""
    best, bd = None, 70 ** 2
    for name, (r, g, b) in legend.items():
        d = (int(px[0]) - r) ** 2 + (int(px[1]) - g) ** 2 + (int(px[2]) - b) ** 2
        if d < bd:
            best, bd = name, d
    return best


def read_stacked(arr, bars, baseline_y, legend):
    """For each bar, walk a central strip from baseline upward; measure each
    colour's segment height in pixels (bottom-up). Returns per-bar dict."""
    out = []
    for (x0, x1) in bars:
        cx = (x0 + x1) // 2
        xs = list(range(x0 + 2, max(x0 + 3, x1 - 1)))      # columns across the bar
        seg = {}
        order = []
        r = baseline_y - 1
        gap = 0
        while r > 0:
            # majority colour across the bar width at this row (robust to a thin
            # central gap / annotation leader line / antialiased edges)
            votes = {}
            for x in xs:
                nm = classify(arr[r, x], legend)
                if nm:
                    votes[nm] = votes.get(nm, 0) + 1
            name = max(votes, key=votes.get) if votes else None
            if name is None:
                gap += 1
                if gap > 6:        # past the top of the bar
                    break
            else:
                gap = 0
                seg[name] = seg.get(name, 0) + 1
                if name not in order:
                    order.append(name)
            r -= 1
        total = sum(seg.values())
        out.append({"x0": x0, "x1": x1, "cx": cx, "segments_px": seg,
                    "order_bottom_up": order, "total_px": total})
    return out


def read_grouped(arr, y_axis_x, baseline_y, legend):
    """GROUPED bars: each product is its own single-colour bar. For each legend
    colour, find the column-runs that sit on the baseline (= that product's bars)
    and measure each bar's height (baseline → top of the colour). Returns a list
    of {product, x0, x1, cx, height_px} sorted left→right."""
    f = arr.astype(int)
    out = []
    for name, (r, g, b) in legend.items():
        dist = (f[:, :, 0] - r) ** 2 + (f[:, :, 1] - g) ** 2 + (f[:, :, 2] - b) ** 2
        mask = dist < 70 ** 2
        band = mask[baseline_y - 9: baseline_y - 1, :].sum(axis=0)
        band[: y_axis_x + 2] = 0
        on = band >= 4
        i = 0
        while i < len(on):
            if not on[i]:
                i += 1
                continue
            j = i
            while j < len(on) and on[j]:
                j += 1
            if j - i >= 4:                       # a bar of this product
                xs = list(range(i + 1, max(i + 2, j - 1)))
                rr, gap, h = baseline_y - 1, 0, 0
                while rr > 0:
                    hit = sum(1 for x in xs if mask[rr, x]) >= max(1, len(xs) // 2)
                    if hit:
                        h += 1; gap = 0
                    else:
                        gap += 1
                        if gap > 6:
                            break
                    rr -= 1
                out.append({"product": name, "x0": i, "x1": j,
                            "cx": (i + j) // 2, "height_px": h})
            i = j
    out.sort(key=lambda d: d["cx"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="CV bar reader")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ip = sub.add_parser("inspect")
    ip.add_argument("--image", required=True)
    ip.add_argument("--crop", choices=["top", "bottom"], default=None)
    rp = sub.add_parser("read", help="read a 2+colour STACKED bar panel")
    rp.add_argument("--image", required=True)
    rp.add_argument("--crop", choices=["top", "bottom"], default=None)
    rp.add_argument("--colors", default="",
                    help="optional 'name:r,g,b;...'; default = top-2 palette colours")
    rp.add_argument("--grouped", action="store_true",
                    help="grouped bars (each product a separate single-colour bar)")
    args = ap.parse_args()

    if args.cmd == "read":
        path = Path(args.image)
        arr = load(path, args.crop)
        y_axis_x, baseline_y, top_y = find_axes(arr)
        if args.colors:
            legend = {}
            for part in args.colors.split(";"):
                nm, rgb = part.split(":")
                legend[nm] = tuple(int(v) for v in rgb.split(","))
        else:
            pal = palette(arr, k=2)
            legend = {f"c{i}": rgb for i, (rgb, _) in enumerate(pal)}
        if args.grouped:
            g = read_grouped(arr, y_axis_x, baseline_y, legend)
            print(f"legend colours: {legend}")
            print(f"grouped bars detected: {len(g)} (left→right)")
            for k, d in enumerate(g):
                print(f"  bar{k} cx={d['cx']:4d}  {d['product']:6s}  "
                      f"height={d['height_px']}px")
            OUT.mkdir(parents=True, exist_ok=True)
            im = Image.fromarray(arr).convert("RGB"); dr = ImageDraw.Draw(im)
            dr.line([(0, baseline_y), (arr.shape[1], baseline_y)], fill=(0, 255, 255))
            for d in g:
                dr.line([(d["cx"], baseline_y - d["height_px"]), (d["cx"], baseline_y)],
                        fill=(255, 0, 255), width=2)
            dbg = OUT / f"{path.stem}_{args.crop or 'full'}_grouped.png"
            im.save(dbg); print(f"debug -> {dbg}")
            return
        bars = detect_bars(arr, y_axis_x, baseline_y)
        res = read_stacked(arr, bars, baseline_y, legend)
        print(f"legend colours: {legend}")
        print(f"bars detected : {len(bars)}  at x={[ (b[0]+b[1])//2 for b in bars]}")
        for i, b in enumerate(res):
            tot = b["total_px"] or 1
            fr = {k: f"{100*v/tot:.1f}%" for k, v in b["segments_px"].items()}
            print(f"  bar{i} (cx={b['cx']}): total={b['total_px']}px  "
                  f"segments(px)={b['segments_px']}  fractions={fr}")
        OUT.mkdir(parents=True, exist_ok=True)
        im = Image.fromarray(arr).convert("RGB"); d = ImageDraw.Draw(im)
        d.line([(0, baseline_y), (arr.shape[1], baseline_y)], fill=(0, 255, 255))
        for b in res:
            d.line([(b["cx"], 0), (b["cx"], baseline_y)], fill=(255, 0, 255))
        dbg = OUT / f"{path.stem}_{args.crop or 'full'}_read.png"
        im.save(dbg)
        print(f"debug -> {dbg}")
        return

    if args.cmd == "inspect":
        path = Path(args.image)
        arr = load(path, args.crop)
        h, w, _ = arr.shape
        y_axis_x, baseline_y, top_y = find_axes(arr)
        ticks = find_yticks(arr, y_axis_x)
        pal = palette(arr)
        print(f"image       : {path.name}  crop={args.crop}")
        print(f"size (h x w) : {h} x {w}")
        print(f"y-axis x px  : {y_axis_x}")
        print(f"baseline y px: {baseline_y}  (= value 0)")
        print(f"plot top y px: {top_y}")
        print(f"y-tick rows  : {ticks}")
        if len(ticks) >= 2:
            sp = np.diff(ticks)
            print(f"  tick spacing px: {list(sp)}  (even spacing ⇒ linear scale)")
        print("dominant saturated colours (RGB, pixel count):")
        for rgb, n in pal:
            print(f"   {rgb}   {n}")
        # debug overlay
        OUT.mkdir(parents=True, exist_ok=True)
        im = Image.fromarray(arr).convert("RGB")
        d = ImageDraw.Draw(im)
        d.line([(y_axis_x, 0), (y_axis_x, h)], fill=(255, 0, 255), width=1)
        d.line([(0, baseline_y), (w, baseline_y)], fill=(0, 255, 255), width=1)
        d.line([(0, top_y), (w, top_y)], fill=(255, 165, 0), width=1)
        for t in ticks:
            d.line([(y_axis_x - 10, t), (y_axis_x, t)], fill=(0, 0, 255), width=1)
        dbg = OUT / f"{path.stem}_{args.crop or 'full'}_inspect.png"
        im.save(dbg)
        print(f"\ndebug overlay -> {dbg}")
        print("(magenta = y-axis, cyan = baseline/value-0, orange = plot top)")


if __name__ == "__main__":
    main()

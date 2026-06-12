# Figure → Data: Design & Roadmap

How the pipeline turns catalysis plots into structured per-catalyst data, and
where the figure track is going. Companion to the **Figure track** in
[../README.md](../README.md).

---

## Motivation

Tables give dense per-catalyst records, but a large share of catalysis
performance lives **only in figures** — line/scatter activity plots, stacked-bar
product distributions, and time-on-stream (TOS) curves. A caption-based scan of
the corpus finds **48 / 51 papers with activity figures** (~150 line/scatter,
~43 bar), against the characterization figures (XRD, NH₃-TPD, IR, Raman, SEM)
that carry no performance data. Recovering the activity figures is therefore the
main lever for growing structure–activity records beyond what tables alone yield.

---

## Design principles

1. **Type first, then read.** Most figures are characterization, not activity.
   Figures are classified from their *caption* (free, deterministic; no API);
   only activity and structure–activity panels go downstream. This gate is the
   cheapest and most reliable step in the track.
2. **Deterministic before model.** A pixel-level OpenCV reader (reproducible, no
   API cost) is preferred over a vision/model backend. A model is reserved for
   panels the deterministic reader cannot resolve.
3. **Keep metrics separate.** Conversion, selectivity, yield, and stability are
   distinct axes and are never merged into a single "performance" axis
   (yield = conversion × selectivity). The reader records each as printed.
4. **Flag, don't guess.** The fragile step is mapping a curve's colour back to a
   catalyst name (legend reading). Low-confidence panels are flagged for human
   verification rather than reported as fact.

---

## Architecture: a pluggable backend

The pipeline owns a single interface and the backends are swappable
(`scripts/extraction/chart_extractor.py`):

```
ChartExtractor.extract(image) → ChartExtraction
  ChartExtraction = panels[]            (one per sub-plot a/b/c…)
    Panel = chart_type, x_axis, y_axis, series[]
      Axis  = label, unit, min, max
      Series = name (= catalyst identity from legend), points[{x, y}]
```

A shared **axis-calibration layer** (axis-line detection + tick-value reading)
converts pixel coordinates to data coordinates and is reused by every backend,
so adding a reader only means producing pixel-space traces.

---

## Current state

| Component | Status | Notes |
|---|---|---|
| Caption typing (`scope_figures.py`) | ✅ done, free | matches expert labels; gates out characterization |
| Bar reader (`bar_reader.py`) | ✅ done, deterministic | stacked + grouped; validated ≤0.5 % (tall segments), ±2–4 % (small). Geometry is accurate; colour→catalyst naming is the fragile part |
| Vision backend (`chart_extractor.py`) | ✅ works | reads line/scatter points where needed; consumes API credit |
| Line/scatter reader (`line_reader.py`) | ✅ v1, deterministic | numpy+Pillow+SciPy+Tesseract: panel split, OCR-calibrated axes (dark-masked per-tick crops, major-tick filter, stub-dash hygiene, validated linear fits), hue-merged colour series, legend OCR, marker/line point extraction. 109/148 scope figures yield series (~16k pts); 56 % of panels have ≥1 calibrated axis, 22 fully calibrated; non-charts refused. Verification HTML re-plots each extraction beside the original (`line_reader.py html`). Known v1 limits: grayscale marker plots (~20 % of scope), black series next to coloured ones, multi-axis panels |

---

## Roadmap

### 1. Model-free line/scatter reader (next)

A deterministic reader for line and scatter plots: coloured-marker detection
(OpenCV) with OCR-calibrated axes (Tesseract), sharing the axis-calibration
layer with the bar reader. The goal is to make figure digitisation **fully
deterministic and API-free**, matching the bar reader.

Known hard cases to handle or flag: overlapping and crossing curves, log axes,
dashed/dotted lines, marker collision, and dense point clouds. Where the reader
degrades, it lowers its confidence and defers to human verification rather than
emitting unreliable points.

### 2. Pure-PyTorch, MMDetection-free LineFormer backend (parked)

For dense or crossing curves that defeat the deterministic reader, a learned
backend is the fallback. The published LineFormer line-chart model depends on
**MMDetection/MMCV**, which is heavy, version-brittle, and awkward to reproduce
or self-host. The plan is to reimplement the useful core in **plain PyTorch**
behind the same `ChartExtractor` interface, so the backend is pip-installable and
reproducible with no MMDetection registry.

Intended approach:

- **Formulation:** per-series line-mask / instance segmentation (one mask per
  curve), or keypoint–heatmap regression of points along each curve.
- **Backbone + head:** a standard PyTorch CNN or compact transformer
  (e.g. ResNet/HRNet or a small ViT) with a segmentation/keypoint head — no
  framework-specific registry.
- **Instance separation:** split overlapping curves by colour/embedding
  clustering or a panoptic-style head.
- **Pixel → data:** reuse the shared axis-calibration layer (tick OCR + linear or
  log transform) — identical to the CV readers.
- **Training data:** a synthetic chart generator (programmatically rendered
  line/scatter with known ground-truth series across styles, colours, noise, and
  axis types) for pretraining; fine-tuning on public chart datasets where
  licensing permits.
- **Validation:** against printed values, with the human-in-the-loop
  verification HTML (`verify_charts.py`).

**Status:** parked on the `feat/lineformer-standalone` branch. It is promoted
only if the deterministic reader proves to be a blocker — empty branches are not
opened ahead of need.

### 3. Route B — interpret the remaining chart types

Route A (the current demo) integrates clean "structure-descriptor vs
performance" panels. The extractor already captures the raw data of the other
activity figures, so Route B is the downstream **interpretation** layer:

- stacked product-distribution bars → per-catalyst product spectrum
  (BTX distribution, p/o ratio);
- time-on-stream curves → stability and deactivation-rate metrics;
- fold both into `catalyst_records`.

These need additional discrimination and normalization logic plus human review,
which is why they follow rather than block Route A. Nothing is lost in the
meantime — the raw data is already captured; only the interpretation layer is
pending.

---

## Guardrails (carried from the table track)

- Never pool conversions or selectivities across the two reactions (MTA vs
  CO₂→aromatics); stratify by reaction and catalyst family.
- Classify figure type before extracting.
- Treat legend/colour→catalyst mapping as the known weak link; surface it for
  verification instead of guessing.

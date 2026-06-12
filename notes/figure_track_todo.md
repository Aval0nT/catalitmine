# Figure Track — living TODO & decision log

*The single source of truth for the figure→data effort. Update every working
session: move items between sections, date the decisions, never delete history.*

*Last updated: 2026-06-12*

**Why this track exists:** structure–activity records are the ML bottleneck
(59 by attributes, 38 numeric) and the missing performance numbers live in
figures — 48/51 papers carry activity figures (~150 line/scatter, ~43 bar).

---

## Architecture (decided 2026-06-12)

**Auto first-pass + HUMAN GATE.** For a dataset, precision of what enters the
DB is everything; recall can be partial. The human verification page is the
gate — automation only determines how much human time each figure costs.
Pure-auto 80–90 % end-to-end reliability is judged unrealistic (long-tail
journal styles); auto + gate reaches ~100 % precision on accepted data by
construction.

Routing cascade (human confirms figure type, then):

```
colored, well-separated line/scatter → line_reader.py (CV, local, instant)
grayscale / black / same-hue pairs / crossing lines → LineFormer (Colab GPU)
bar charts → bar_reader.py (validated ≤0.5 %)
all → verification HTML → human: accept / fix / reject
```

Semantic layer (axis calibration + legend names) is NOT solved by any of the
geometry models — it stays OCR + human clicks regardless of route.

---

## NOW — in flight

- [ ] **LineFormer → HF standalone port** *(owner: Claude; GREENLIT by
      Yuang 2026-06-12 after reviewing the 3-way page: "traces 非常准确";
      noted weakness on very light colours — tune via input contrast
      preprocessing later, tracked below)*.
      Phase 1 DONE (2026-06-12): checkpoint at
      models/lineformer_mmdet/iter_3000.pth (570 MB, gitignored; meta
      CLASSES=('line',), mmdet 2.28.2, iter 3000). Census verdict:
      MECHANICAL — pixel_decoder 117 = 117 keys EXACT vs HF
      facebook/mask2former-swin-tiny-coco-instance (num_labels→1;
      queries=100 ✓ hidden=256 ✓ Swin-T ✓); encoder 189/237 and decoder
      164/206 count gaps are HF-side buffers (relative_position_index etc.).
      torch 2.8 loads the ckpt with weights_only=False.
      Phase 2 (next session): name-level mapping script → load into HF →
      logits/mask parity against the 30 Modal probe outputs
      (figures/lineformer_probe_results/output/*/lineformer/coordinates.json
      is the golden reference).
      Phase 3: port line_utils post-processing (pure scipy/skimage) and
      register as a chart_extractor backend.
- [ ] light-colour trace dropout — try contrast/CLAHE preprocessing before
      inference once the port runs locally (user observation from the probe
      review).
- [~] ~~Three quick fixes to line_reader~~ *(deprioritized 2026-06-12: the
      route moved to LineFormer-first, so standalone CV-reader fixes lose
      value; y-flip folded into the fusion display above, junk-name filter
      and bar/line routing revisit only if the CV reader stays in the
      cascade after the probe verdict)*

## NEXT — queued, order flexible

- [ ] **Gold-set triage query** — from the DB: which figures, if digitized,
      JOIN against existing property records into structure–activity records?
      Target the valuable ~20–40 figures, not all 148.
- [ ] **Click-to-calibrate UI** — upgrade the verification HTML: click two
      ticks + type two values per axis, JS recomputes all points from the
      stored pixel traces, edit series names, export corrected JSON.
      Prerequisite: keep `_box`/`_offset` (pixel transform) in saved JSON.
      By-product: every corrected figure = ground truth for training/eval.
- [ ] **Benetech 2nd-place test drive** — run the open Kaggle solution
      (rbiswasfc/benetech-mga) on our scatter panels: free starting point,
      wrong domain (K-12-style charts), but measures the gap.
- [ ] **Vision-semantic option** (needs ~$5 API top-up, user decision):
      Haiku reads axis ranges + legend names (its strength), CV keeps the
      geometry (its strength). 148 figures ≈ $2–5 once.

## LATER — only if the probe/tests justify it

- [ ] **MarkerFormer v1** (the "ScatterFormer" idea — name taken by a CVPR'24
      3D-point-cloud paper, rename on release): marker detection + shape
      classification (circle/square/triangle × open/filled). Verdict from
      2026-06-12 evaluation: FEASIBLE and simpler than LineFormer's task.
      Recipe (Benetech-winner standard):
  - [ ] synthetic chart generator — matplotlib renders ∞ labelled scatter
        plots in catalysis-journal styles (serif fonts, JPEG artefacts,
        grayscale, dual axes, gridlines)
  - [ ] train YOLO-s/DETR-small on synthetic (Colab T4 / Kaggle P100 free
        tier is sufficient)
  - [ ] fine-tune + eval on the human-gate gold set (the correction UI
        produces it for free)
  - realistic v1 effort: 2–4 weeks part-time; burns GPU-hours (free), not
    tokens
- [ ] **ColumnFormer: probably NOT needed** — bars are deterministic-CV
      territory (bar_reader validated); the gap is only grayscale/hatched
      fills → add texture discrimination to bar_reader instead of a model.
- [ ] **LineFormer standalone port** (MMDetection-free) — DE-RISKED
      2026-06-12: the config reveals LineFormer is 100% STOCK Mask2Former
      (Swin-T + Mask2FormerHead, no custom layers); the post-processing
      (line_utils: skeletonize + cubic splines) is pure scipy/skimage.
      Port = checkpoint key-mapping into HF transformers'
      Mask2FormerForUniversalSegmentation (any python/torch, zero mmcv)
      + preprocessing params from the config; ~1-2 weeks part-time.
      Parity test against the Modal probe outputs (which is one more reason
      to run the probe first). Fallback: mmdet 3.x migration (days, but
      stays in the version-fragile OpenMMLab world). Forward-porting
      mmcv-full 1.x to py3.12 is confirmed a dead end.
- [ ] Route B interpretation layer (product-distribution bars → product
      spectra; TOS curves → deactivation metrics) — see
      figure_reader_design.md.
- [ ] `.cvline.json` → `build_structure_activity.py` integration (it
      currently consumes `.chart.json` from the vision backend only).

## DONE

- [x] 2026-06-12 — **line_reader.py v1** (commit 632029a): deterministic
      line/scatter reader (numpy+Pillow+SciPy+Tesseract, no model/API).
      Corpus: 109/148 figures yield series (~16k pts), 22 panels fully
      calibrated, 56 % ≥1 axis; 6 non-charts refused. Verification HTML
      with side-by-side re-plots: `outputs/reports/line_reader_verify.html`.
- [x] 2026-06-12 — 16-figure failure-mode diagnosis (agent fan-out) →
      dark-masked OCR crops, major-tick filter, stub-dash hygiene,
      clause-aware fixes, exact-zero gutters, chartness gate.
- [x] 2026-06-12 — LineFormer probe kit: `figures/lineformer_probe.zip`
      (30 images) + batch Colab notebook (commit 4c9beb3).
- [x] 2026-06-12 — landscape research (see Findings below).
- [x] 2026-06-12 — **LineFormer probe EXECUTED via Modal** (runner commit
      ed7496e + timeout/import self-heal patches): 30/30 images processed on
      the pinned py3.10/torch1.13 container. Headline: the GRAYSCALE catcom
      TOS figure — CV reader: 0 series — LineFormer traced ALL 6 series,
      separating open vs filled black markers and following the crossing in
      panel c. Dense multi-line 119912: 8-12 traces/panel. Marker-only
      scatter (jcat.2015.01): 0 — confirmed dead zone (it is a LINE model)
      → MarkerFormer case strengthened. The wrapper's own axis fusion
      completed on only 7/30 (semantic layer stays ours / human gate).
- [x] 2026-06-12 — 3-way comparison page (commit e992173):
      outputs/reports/lineformer_probe_compare.html, incl. the pixel-y
      orientation fix for CV re-plots.
- [x] 2026-06-12 — **parse-once infrastructure** (commit dd6e858):
      docling_cache + parse_pdfs --workers N; every PDF converts exactly once
      (tables + figures + markdown from one parse), all extractors read the
      cache. Re-ingest 0.06 s, v2 parse 0.3 s; 200-paper corpus ≈ 30 min once.
      Equivalence proven (10/10 tables byte-identical, 69/69 DB rows);
      adversarial review fixed 8 cache-lifecycle/concurrency defects.
- [x] 2026-06-03 — bar_reader.py validated (≤0.5 % tall segments, ±2–4 %
      small); caption-based figure scoping (free, no API).

---

## Findings & decisions log

**2026-06-12 — honest reliability assessment.** Component metrics ("56 % of
panels have ≥1 calibrated axis") badly overstate end-to-end usability —
five stages multiply (split × axes × series × names × points). User review
of the verification page: effectively no figure fully usable yet. Conclusion:
stop heuristic whack-a-mole (fixes regress each other — observed twice);
adopt the human-gate architecture above.

**2026-06-12 — corpus census** (148 line/scatter-scoped figures): ~75 %
coloured & big enough for colour-based CV; ~20 % grayscale marker-shape
series (CV structurally blind — needs LineFormer-class or shape models);
~5 % tiny. Caption-based shape guess is noisy: several "line/scatter" are
bar-dominated combos, spectra, schemes, or micrograph collages — the
chartness gate now refuses non-charts; bar/line panel routing still TODO.

**2026-06-12 — C15/C40 example dissection** (user-reported total failure):
(1) re-plot trend mirrored = uncalibrated pixel-y not flipped (trivial bug);
(2) bar panel traced as lines = missing type routing; (3) junk legend names
from in-plot coloured text + same-hue open/filled marker pairs. Two quick
fixes + one architecture gap — but the long-tail verdict stands.

**2026-06-12 — what LineFormer does and does not solve.** Instance
segmentation of LINE traces: colour-independent (grayscale ✓, black ✓,
crossing ✓) — exactly the CV reader's blind spots. Does NOT do axes, legends,
panel split, bar charts; possibly weak on marker-only scatter (it is a line
model) — probe question #3.

**2026-06-12 — landscape.** Closest existing work: Benetech "Making Graphs
Accessible" Kaggle (2023) — same task shape (type classification +
line/scatter/dot/bar extraction), winning solutions open-sourced
(rbiswasfc/benetech-mga = 2nd place; MatCha/Donut fine-tunes), but trained on
K-12-style charts (private LB 0.72) → domain gap to journal figures is the
real obstacle, no turnkey weights exist for our domain. Geometry-detector
lineage: Scatteract (2017), ChartDete, OsmLocator (overlapping markers).
Strategic read: the OPPORTUNITY is precisely that no open, journal-domain
chart-extraction suite exists — synthetic-data + small-detector + human-gate
benchmark is publishable infrastructure (Digital Discovery material) and
fits the "builds ML infrastructure for chemistry data" narrative.

**2026-06-12 — cost model.** This route burns free GPU-hours and human gate
time, NOT API tokens. Optional vision-semantic pass ≈ $2–5 total. Dev
iteration (agent fleets) is the actual token cost driver.

---

## Open decisions

- [ ] After probe: LineFormer as Colab-notebook official path vs standalone
      rewrite vs drop (→ MarkerFormer-first)?
- [ ] Vision-semantic pass: top up ~$5 API credit, or stay zero-cost with
      manual calibration UI only?
- [ ] Gold-set size & acceptance bar for the first structure–activity
      expansion from figures (target: 38 numeric SA records → 100+?).

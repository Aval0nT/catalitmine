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
      Phase 2 DONE (2026-06-12): conversion + parity PASSED. Mapping script
      scripts/extraction/lineformer_port/convert_lineformer_to_hf.py consumes
      all 481 ckpt tensors → 565/566 HF keys (the one gap is the loss-time
      buffer criterion.empty_weight, rebuilt from config); three real
      transforms (Swin fused qkv split, PatchMerging unfold→group channel
      permutation, decoder self-attn in_proj split), rest renames;
      relative_position_index buffers in the ckpt equal HF's fresh ones
      bit-for-bit (window conventions agree). Output: models/lineformer_hf/
      (gitignored). Parity vs the 30 Modal goldens
      (parity_probe.py → figures/lineformer_probe_results/hf_parity_report.json):
      instance counts 30/30 EXACT incl. the four 0-line scatter rejections;
      point coverage 1.00 on clean single panels (8 images ≥0.95), mean 0.80;
      the low tail is confined to full composites (decorative arrows, 1-px
      downscaled dense panels) and the marker-scatter dead zone, where the
      golden-vs-HF distance histogram is bimodal (44 % at 0–1 px, 4 % at
      1–3 px, 40 % >10 px on the worst dense composite) — whole segments
      reassigned between near-tie queries, not a systematic shift. Read:
      GPU-vs-CPU float noise amplified by 9 rounds of hard-thresholded masked
      attention, not a mapping bug; panel crops (the actual cascade input)
      sit at the top of the distribution.
      Phase 3 DONE (2026-06-12): post-processing reimplemented
      (lineformer_port/line_postproc.py — written from the algorithm, not
      translated, upstream has NO license; quirks deliberately preserved:
      multi-run columns skipped, (first+last)//2 centers, 10-px comb with
      exclusive end, int-truncating per-x linear densify; needs only
      numpy/scipy — skeletonize/bresenham are on the post_proc=True path the
      probe never used). END-TO-END COORDINATE PARITY vs all 30 goldens
      (parity_coords.py → hf_coord_parity.json): 125/129 lines BIT-IDENTICAL,
      4 lines mae 0.04–0.45 px, overlap 1.0 on every pair — the Phase 2
      mask-level divergence lives entirely in multi-run columns that the
      keypoint sampler skips on both sides, so the post-processing quotients
      out the near-tie noise. Registered as chart_extractor backend
      "lineformer" (writes .lfline.json; pixel-space output stays out of the
      value-space .chart.json stream; cv-line CLI path likewise isolated to
      .cvchart.json). Adversarial review (17-agent workflow): 1 major
      confirmed & fixed — instance ORDER diverged from upstream (whose
      topk(sorted=False) order is GPU implementation-defined → order is now
      deterministic descending-cls-score and explicitly excluded from the
      parity contract; consumers must not attach identity to position) —
      plus 9 minors fixed (empty-golden-line handling in both parity
      metrics, float-x crash, NaN guards, model-load error path, sys.path
      hygiene, README/STRUCTURE drift); 4 findings refuted on verification.
      LineFormer now runs locally on CPU: mmcv/mmdet/Modal no longer needed
      for inference. Remaining wiring (queued in NEXT): caption-prior
      panel-crop routing before the model, axis fusion / human-gate display
      for .lfline.json.
- [ ] light-colour trace dropout — try contrast/CLAHE preprocessing before
      inference once the port runs locally (user observation from the probe
      review).
- [~] ~~Three quick fixes to line_reader~~ *(deprioritized 2026-06-12: the
      route moved to LineFormer-first, so standalone CV-reader fixes lose
      value; y-flip folded into the fusion display above, junk-name filter
      and bar/line routing revisit only if the CV reader stays in the
      cascade after the probe verdict)*

## NEXT — queued, order flexible

*Cross-cutting input (added 2026-06-13, user observation): CAPTIONS are a
first-class signal, not just a type-guess source. Coverage measured: 472/974
figure crops carry a non-empty Docling caption, 228 spell out the panel
inventory ("(a) ..., (b) ..."). One caption typically names the catalysts
(the triage JOIN key), the plotted quantities (axis semantics), the panel
count/content (routing prior), and often reaction conditions (T, TOS). The
three items below each consume it; the geometry models never see it.*

- [ ] **Gold-set triage query** — CAPTION-DRIVEN: match catalyst names in
      caption text against existing property records in the DB, and filter
      panels by performance keywords (conversion/selectivity/yield/TOS) vs
      characterization (SEM/XRD/NMR/TGA — skip). Which figures, if digitized,
      JOIN into structure–activity records? Target the valuable ~20–40
      figures, not all 148. Also produce a caption-coverage diagnostic
      (502/974 crops have empty captions — partly real non-figures
      [schemes, graphical abstracts], partly Docling capture misses;
      quantify before trusting the filter as an exclusion gate).
- [ ] **Panel-crop routing before LineFormer** — composites lose ~0.3
      coverage at 512 px (Phase 2 data); split into panels first. Use the
      caption's panel inventory as PRIOR + VALIDATION for the visual
      splitter: caption says 2 panels but splitter finds 3 → flag for the
      human gate; per-panel caption text routes each crop (line panel →
      lineformer backend, bar panel → bar_reader, spectra/microscopy →
      skip). Captions give count + content, never pixel boundaries — the
      visual split stays, caption arbitrates.
- [ ] **Click-to-calibrate UI** — upgrade the verification HTML: click two
      ticks + type two values per axis, JS recomputes all points from the
      stored pixel traces, edit series names, export corrected JSON.
      Prerequisite: keep `_box`/`_offset` (pixel transform) in saved JSON.
      PRE-FILL from caption: candidate series/catalyst names, axis
      quantities, conditions — the human confirms instead of typing.
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

**2026-06-12 — HF-port parity: what "equal" means for a Mask2Former.**
Bit-identical outputs across stacks are unattainable by construction: the
decoder re-thresholds (sigmoid < 0.5) intermediate masks for masked attention
9 times, so ~1e-6 float differences (CUDA MSDA kernel vs torch grid_sample,
GPU vs CPU convs) flip attention discretely wherever a mask pixel sits near
the boundary — i.e. exactly at line crossings and 1-px features. The right
acceptance test is therefore behavioral: instance counts, scores, and
coverage on confident regions (all passed; see NOW). Implication for the
cascade: feed LineFormer panel CROPS, not full composites — fulls lose
≈0.3 coverage to downscaling at 512 px while their own crops score 0.85–1.00.

**2026-06-12 — LineFormer licensing / release facts** (user asked whether the
port can become "our own fork"). github.com/TheJaeLal/LineFormer has NO
LICENSE file → default all-rights-reserved; the README invites use + citation
but grants nothing formally (the vendored mmdetection/ subtree is Apache-2.0,
OpenMMLab's). Weights: authors distribute via Google Drive (no license);
the HF mirror tdsone/lineformer is tagged MIT by a third party who cannot
grant it — though the authors' own README links to that wrapper approvingly
(good-faith signal, not a license). Our position: convert_lineformer_to_hf.py
+ lineformer_hf_infer.py are original work; line_postproc.py reimplements the
published algorithm (algorithms are not copyrightable; expression is — ours).
After Phase 3 the runtime depends on zero upstream code. Release options,
clean → cleanest: (a) own repo with conversion SCRIPTS only (user fetches
weights from the authors' channel, converts locally) — needs nobody's
permission; (b) same + converted weights on HF Hub — write the authors first;
(c) a literal GitHub fork — wrong vehicle: inherits the unlicensed status AND
the dead mmdet stack. Cite the ICDAR 2023 paper in all cases.

**2026-06-12 — cost model.** This route burns free GPU-hours and human gate
time, NOT API tokens. Optional vision-semantic pass ≈ $2–5 total. Dev
iteration (agent fleets) is the actual token cost driver.

---

## Open decisions

- [ ] ~~After probe: LineFormer as Colab-notebook official path vs standalone
      rewrite vs drop?~~ RESOLVED 2026-06-12: standalone HF port, done
      (Phases 1–3). New decision: PUBLIC RELEASE vehicle — own repo with
      conversion scripts only (zero-permission), or + converted weights on
      HF Hub (email the LineFormer authors first; see licensing facts in
      the findings log). A GitHub fork is the wrong vehicle either way.
- [ ] Vision-semantic pass: top up ~$5 API credit, or stay zero-cost with
      manual calibration UI only?
- [ ] Gold-set size & acceptance bar for the first structure–activity
      expansion from figures (target: 38 numeric SA records → 100+?).

"""line_postproc.py — instance masks → per-line point series (LineFormer Phase 3).

Behavioral reimplementation of the keypoint-extraction stage published with
LineFormer (Lal et al., ICDAR 2023, github.com/TheJaeLal/LineFormer —
infer.get_dataseries + line_utils, post_proc=False path). Written from the
algorithm, not translated from their code (the upstream repo carries no
license); quirks are preserved DELIBERATELY because the Modal probe goldens
were produced by the original implementation and Phase 3 parity is judged
against them:

  * the x-extent of a mask is the first..last column whose 5-tap
    median-filtered column-occupancy is nonzero, and the per-column sweep is
    range(x0, x1, 10) — exclusive of x1, so the final column is sampled only
    when it falls on the 10 px grid;
  * within a column, foreground rows split into runs wherever the vertical
    gap exceeds 2 px; columns with more than one run (crossings, markers,
    dashes mid-gap) contribute NO point;
  * a single-run column yields its run midpoint (first+last)//2 — floor;
  * fewer than two sampled points: the raw sampled points are returned
    as-is (x stays float, no interpolation);
  * otherwise the points are linearly interpolated and re-sampled at every
    integer x in [x_min, x_max], y truncated to int;
  * degenerate masks still emit their (possibly empty) series — callers
    rely on one output entry per input mask.

No skimage/bresenham needed on this path — numpy + scipy.signal/interpolate.
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import interp1d
from scipy.signal import medfilt

SAMPLE_INTERVAL = 10  # px between sampled columns (upstream default)
MAX_RUN_GAP = 2       # vertical gap (px) tolerated inside one run


def column_extent(mask: np.ndarray) -> tuple[int, int] | None:
    """First/last column index with nonzero median-filtered occupancy."""
    occupancy = medfilt(mask.astype(np.uint8).sum(axis=0), kernel_size=5)
    nz = np.flatnonzero(occupancy)
    if nz.size == 0:
        return None
    return int(nz[0]), int(nz[-1])


def single_run_center(column: np.ndarray) -> int | None:
    """Midpoint of the column's foreground run, or None if 0 or 2+ runs."""
    rows = np.flatnonzero(column)
    if rows.size == 0:
        return None
    if (np.diff(rows) > MAX_RUN_GAP).any():  # 2+ runs -> ambiguous, skip
        return None
    return int(rows[0] + rows[-1]) // 2


def sample_keypoints(mask: np.ndarray, interval: int = SAMPLE_INTERVAL) -> list[dict]:
    """One {x, y} per sampled single-run column (pixel coordinates)."""
    extent = column_extent(mask)
    x0, x1 = extent if extent is not None else (0, mask.shape[1])
    points = []
    for x in range(x0, x1, interval):
        y = single_run_center(mask[:, x])
        if y is not None:
            points.append({"x": float(x), "y": y})
    return points


def densify(points: list[dict]) -> list[dict]:
    """Linear interpolation onto every integer x spanned by the keypoints."""
    if len(points) < 2:
        return points
    xs = [int(pt["x"]) for pt in points]
    ys = [int(pt["y"]) for pt in points]
    line = interp1d(xs, ys)
    return [{"x": x, "y": int(line(x))} for x in range(min(xs), max(xs) + 1)]


def masks_to_dataseries(masks: np.ndarray) -> list[list[dict]]:
    """bool (N, H, W) instance masks -> N point series, original-image pixels.

    Same output contract as the Modal probe's coordinates.json: a list per
    mask (possibly empty), each a list of {"x": int, "y": int} at unit-x
    spacing — except degenerate (<2 keypoint) masks, which keep float x.
    """
    return [densify(sample_keypoints(m)) for m in masks]

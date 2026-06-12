"""
lineformer_modal_probe.py — run the LineFormer probe on Modal's GPU cloud.

Why Modal instead of Colab: current Colab images (Python 3.12 / torch 2.10)
can no longer install the MMDetection-era stack LineFormer needs. The
plextract wrapper ships a Modal backend whose CONTAINER IMAGE pins the whole
stack (Python 3.10, torch 1.13.1, mmcv-full 1.x) — the environment fight is
solved once, server-side. The client needs only the `modal` package.

One-time setup:
  1. sign up at https://modal.com (GitHub/Google login; free tier credits)
  2. .venv-modal/bin/modal token new          # opens the browser once
Run:
  .venv-modal/bin/python3 scripts/extraction/lineformer_modal_probe.py

First run also BUILDS the pinned image on Modal's side (~5-10 min, cached
afterwards). Results land in figures/lineformer_probe_results/.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "third_party" / "extract-line-chart-data"
PROBE = ROOT / "figures" / "lineformer_probe"
OUT = ROOT / "figures" / "lineformer_probe_results"

# plextract pins python >=3.10,<3.11 in pip metadata, but the modal-backend
# client code itself runs fine on 3.11 — import from source, bypassing pip
sys.path.insert(0, str(WRAPPER / "src"))
# download_volume_dir shells out to the `modal` CLI — make sure THIS venv's
# bin dir wins the PATH lookup
os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]


def main() -> None:
    assert WRAPPER.exists(), f"wrapper repo missing — git clone tdsone/extract-line-chart-data into {WRAPPER}"
    pngs = sorted(PROBE.glob("*.png"))
    assert pngs, f"probe images missing under {PROBE}"

    # stage only the single-panel crops + full composites (same set as the zip)
    staging = ROOT / "figures" / "_modal_probe_input"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for p in pngs:
        shutil.copy(p, staging / p.name)
    print(f"staged {len(pngs)} probe images → {staging}")

    OUT.mkdir(parents=True, exist_ok=True)
    from plextract import extract
    extract(input_dir=str(staging), output_dir=str(OUT), backend="modal")

    n = sum(1 for _ in OUT.rglob("*.json"))
    print(f"\ndone — {n} result JSONs under {OUT}")
    print("next: tell Claude; the fusion + 3-way verification HTML starts from here")


if __name__ == "__main__":
    main()

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


def _patch_wrapper() -> None:
    """Self-heal known wrapper issues (idempotent).

    1. modal >=1.5 removed the long-deprecated `modal.gpu` module; the wrapper
       imports it but never uses it (gpu= is always passed as a string).
    2. Modal's default per-function timeout is 300 s — the orchestrating
       run_pipeline (and the model classes) need more for a 30-image batch
       with three cold container starts (observed: pipeline healthy, killed
       at exactly 300 s)."""
    fixes = [
        ("modal/lineformer.py",
         "from modal import App, gpu, method",
         "from modal import App, method"),
        ("modal/app.py",
         '@modal_app.function(image=image, volumes={"/data": vol})',
         '@modal_app.function(image=image, volumes={"/data": vol}, timeout=3600)'),
        ("modal/lineformer.py",
         '@app.cls(\n    gpu="any",\n    scaledown_window=240,\n    image=lineformer_image,',
         '@app.cls(\n    gpu="any",\n    scaledown_window=240,\n    timeout=1800,\n    image=lineformer_image,'),
        ("modal/trocr.py",
         '@app.cls(\n    image=ocr_img,',
         '@app.cls(\n    timeout=1800,\n    image=ocr_img,'),
    ]
    for rel, old, new in fixes:
        f = WRAPPER / "src" / "plextract" / rel
        src = f.read_text(encoding="utf-8")
        if old in src:
            f.write_text(src.replace(old, new), encoding="utf-8")
            print(f"patched wrapper: {rel} ({new.splitlines()[-1].strip()[:50]}…)")


def main() -> None:
    assert WRAPPER.exists(), f"wrapper repo missing — git clone tdsone/extract-line-chart-data into {WRAPPER}"
    _patch_wrapper()
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

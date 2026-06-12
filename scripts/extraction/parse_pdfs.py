"""
parse_pdfs.py — parallel one-time Docling parse of the corpus (the heavy step).

Runs docling_cache.parse_pdf over every requested PDF with a worker pool, so
the most expensive stage of the pipeline (~30-60 s per paper, embarrassingly
parallel) happens once and in parallel. After this, ingest_tables,
scope_figures, and extract_docling_v2 all read the cache and finish in
seconds. Workers touch only the filesystem — no DB contention.

  python3 scripts/extraction/parse_pdfs.py --from-pdfs --workers 6
  python3 scripts/extraction/parse_pdfs.py 10.1016/j.jcat.2018.03.032
  python3 scripts/extraction/parse_pdfs.py --from-pdfs --force   # reparse all
"""
from __future__ import annotations

import argparse
import sys
import time
from multiprocessing import get_context
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import docling_cache                                   # noqa: E402
from ingest_tables import find_pdf, find_si_pdfs, pdf_dois  # noqa: E402

_CONVERTER = None


def _init_worker() -> None:
    """Load the Docling models once per worker process."""
    global _CONVERTER
    _CONVERTER = docling_cache._make_converter()


def _job(args: tuple) -> tuple:
    path_s, stem, with_figures, force = args
    pdf = Path(path_s)
    t0 = time.time()
    try:
        if not force and docling_cache.is_fresh(stem, pdf):
            return (stem, "cached", 0.0)
        docling_cache.parse_pdf(pdf, stem=stem, converter=_CONVERTER,
                                with_figures=with_figures)
        return (stem, "parsed", time.time() - t0)
    except Exception as e:
        return (stem, f"error: {e}", time.time() - t0)


def prewarm(dois: list[str], workers: int = 4, force: bool = False) -> dict:
    """Parse every uncached document for these DOIs (main PDFs + PDF SI) with
    a worker pool. Importable: ingest_tables --workers N calls this before its
    serial (cache-fed) ingest."""
    # fail fast in the PARENT: a worker initializer that raises (e.g. docling
    # not installed) makes the spawn pool respawn workers forever and hang
    import importlib.util
    if importlib.util.find_spec("docling") is None:
        raise SystemExit("docling is not installed in this environment — "
                         "run `pip install -r requirements.txt` first")

    jobs, seen = [], set()
    for doi in dois:
        pdf = find_pdf(doi)
        if not pdf:
            print(f"  · no PDF for {doi}")
            continue
        # cache MAIN papers under the DOI slug, not pdf.stem: suffix-named
        # PDFs ("<slug> (1).pdf") must land where scope_figures looks them up
        slug = doi.replace("/", "_")
        if slug not in seen:                     # never two workers on one cache dir
            seen.add(slug)
            jobs.append((str(pdf), slug, True, force))
        for si in find_si_pdfs(doi):
            if si.suffix.lower() == ".pdf" and si.stem not in seen:
                seen.add(si.stem)                # docx SI handled by ingest directly
                jobs.append((str(si), si.stem, False, force))

    print(f"{len(jobs)} documents, {workers} workers "
          f"(each worker loads Docling once)\n")
    t0 = time.time()
    done = cached = failed = 0
    # spawn: fork is unsafe with torch/Accelerate on macOS
    ctx = get_context("spawn")
    with ctx.Pool(processes=workers, initializer=_init_worker) as pool:
        for stem, status, secs in pool.imap_unordered(_job, jobs):
            mark = ("·" if status == "cached"
                    else "✓" if status == "parsed" else "✗")
            print(f"  {mark} {stem[:58]:58s} {status[:40]:40s} {secs:5.1f}s")
            done += status == "parsed"
            cached += status == "cached"
            failed += status.startswith("error")
    print(f"\n{done} parsed, {cached} already cached, {failed} failed "
          f"in {time.time() - t0:.0f}s → {docling_cache.PARSED}")
    return {"parsed": done, "cached": cached, "failed": failed}


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse PDFs once with Docling (parallel)")
    ap.add_argument("dois", nargs="*", help="DOIs (either form)")
    ap.add_argument("--from-pdfs", action="store_true",
                    help="every DOI-named PDF under topics/*/pdfs/")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true", help="reparse even if cached")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    dois = list(args.dois)          # find_pdf accepts both DOI forms
    if args.from_pdfs:
        dois += [d for d in pdf_dois() if d not in dois]
    if args.limit:
        dois = dois[: args.limit]
    if not dois:
        raise SystemExit("no DOIs (pass DOIs or --from-pdfs)")
    stats = prewarm(dois, workers=args.workers, force=args.force)
    if stats["failed"]:
        raise SystemExit(1)          # shell pipelines must see the failure


if __name__ == "__main__":
    main()

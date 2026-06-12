"""
docling_cache.py — parse each PDF with Docling ONCE; every extractor eats the cache.

Docling conversion is the most expensive step in the pipeline (~30–60 s per
paper), and three consumers used to each run their own conversion of the same
PDF: ingest_tables (tables), extract_figures/scope_figures (figure crops +
captions), extract_docling_v2 (sections + tables). This module runs ONE
conversion with the superset of options and writes plain, version-independent
artifacts that all three read:

  data/00_parsed/<stem>/
    doc.md         markdown export (sections + references are derived from it)
    tables.json    [{doc_index, caption, page, headers, rows}] — strings, in
                   original doc order, with the 1-based index over doc.tables
                   preserved so table numbering (and therefore row_ids) stays
                   identical to a direct parse
    meta.json      freshness key: pdf path/mtime/size + docling version
  figures/all_charts/<stem>/
    <stem>_figNN_pP.png + <stem>.captions.json   (the existing figure-cache
                   layout — written via extract_figures.extract on the same
                   converted document)

Batch/parallel front-end: scripts/extraction/parse_pdfs.py.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARSED = ROOT / "data" / "00_parsed"
ALL_CHARTS = ROOT / "figures" / "all_charts"

IMAGES_SCALE = 2.0   # superset option: figure crops need it, tables don't mind


# ── freshness ────────────────────────────────────────────────────────────────

def _docling_version() -> str:
    # the docling package does not export __version__ — read the dist metadata,
    # or the version freshness key silently degrades to "?" == "?"
    try:
        from importlib.metadata import version
        return version("docling")
    except Exception:
        return "?"


def cache_dir(stem: str) -> Path:
    return PARSED / stem


def is_fresh(stem: str, pdf: Path) -> bool:
    """Cache valid for this exact file and docling version."""
    meta_p = cache_dir(stem) / "meta.json"
    if not meta_p.exists():
        return False
    try:
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        st = pdf.stat()
        ok = (meta.get("pdf_name") == pdf.name
              and meta.get("pdf_mtime") == int(st.st_mtime)
              and meta.get("pdf_size") == st.st_size
              and meta.get("docling_version") == _docling_version()
              and meta.get("images_scale") == IMAGES_SCALE)
        if ok and meta.get("with_figures") and meta.get("figures_ok"):
            # the figure crops are part of the cached unit — if the user
            # pruned figures/all_charts/<stem>/, the cache must read stale so
            # the next parse regenerates them
            ok = (ALL_CHARTS / stem / f"{stem}.captions.json").exists()
        return ok
    except Exception:
        return False


# ── the single conversion ────────────────────────────────────────────────────

def _make_converter():
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.base_models import InputFormat
    opts = PdfPipelineOptions()
    opts.images_scale = IMAGES_SCALE
    opts.generate_picture_images = True
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def parse_pdf(pdf: Path, stem: str | None = None, converter=None,
              with_figures: bool = True) -> Path:
    """Convert once, write all artifacts. Returns the cache dir.

    `converter` lets a worker pool reuse one loaded model across PDFs.
    `with_figures=False` skips the figure crops (e.g. for SI documents, whose
    figures are not part of the figure track)."""
    stem = stem or pdf.stem
    out = cache_dir(stem)
    out.mkdir(parents=True, exist_ok=True)
    # invalidate the PREVIOUS generation first: an interrupted RE-parse must
    # not leave old meta.json blessing a half-rewritten artifact mix
    (out / "meta.json").unlink(missing_ok=True)
    # stat BEFORE the minutes-long conversion: if the file is replaced while
    # we parse, the stored stat then mismatches and the cache reads stale
    st = pdf.stat()
    if converter is None:
        converter = _make_converter()
    result = converter.convert(pdf)
    doc = result.document

    # 1. markdown (sections + reference parsing derive from it)
    (out / "doc.md").write_text(doc.export_to_markdown(), encoding="utf-8")

    # 2. tables — preserve original 1-based doc order; stringify once, the way
    #    BOTH consumers did (ingest: str(); v2 reads them back as strings)
    tables = []
    for ti, tbl in enumerate(doc.tables, 1):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = tbl.export_to_dataframe(doc)
        except Exception:
            try:
                df = tbl.export_to_dataframe()
            except Exception:
                continue
        if df is None or df.empty:
            continue
        caption = ""
        try:
            caption = tbl.caption_text(doc) or ""
        except Exception:
            pass
        page = None
        try:
            if tbl.prov:
                page = tbl.prov[0].page_no
        except Exception:
            pass
        tables.append({
            "doc_index": ti,
            "caption": caption,
            "page": page,
            "headers": [str(c) for c in df.columns],
            "rows": [[("" if v is None else str(v)) for v in row]
                     for row in df.itertuples(index=False, name=None)],
        })
    (out / "tables.json").write_text(
        json.dumps(tables, ensure_ascii=False), encoding="utf-8")

    # 3. figures — reuse extract_figures' writer on the SAME document, into
    #    the existing all_charts cache layout. A figure-crop failure must not
    #    abort table/prose caching (it is a side artifact for those tracks).
    figures_ok = False
    if with_figures:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from extract_figures import extract as fig_extract
        try:
            fig_extract(pdf, ALL_CHARTS / stem, scale=IMAGES_SCALE, stem=stem,
                        doc=doc)
            figures_ok = True
        except Exception as e:
            print(f"    [figure extraction failed: {e} — tables/prose cached anyway]")

    # 4. freshness key — written LAST, so an interrupted parse is never fresh
    (out / "meta.json").write_text(json.dumps({
        "pdf_name": pdf.name, "pdf_path": str(pdf),
        "pdf_mtime": int(st.st_mtime), "pdf_size": st.st_size,
        "docling_version": _docling_version(),
        "images_scale": IMAGES_SCALE,
        "n_tables": len(tables),
        "with_figures": bool(with_figures),
        "figures_ok": figures_ok,
    }, indent=2), encoding="utf-8")
    return out


# ── readers (no docling import needed) ───────────────────────────────────────

def load_tables(stem: str):
    """[(doc_index, caption, headers, rows, page)] — ingest_tables' tuple shape."""
    p = cache_dir(stem) / "tables.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    return [(t["doc_index"], t["caption"], t["headers"], t["rows"], t["page"])
            for t in data]


def load_markdown(stem: str) -> str:
    return (cache_dir(stem) / "doc.md").read_text(encoding="utf-8")

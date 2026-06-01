"""
diagnose_tables.py — does Docling actually see tables in our no-table PDFs?

Runs Docling table extraction (identical to extract_docling_v2._extract_tables)
on a list of DOIs and reports, per paper, how many tables Docling finds and a
preview of each. Distinguishes two failure modes:

  - Docling FINDS tables here  → the DB simply never ran v2 table extraction on
    these papers (old pipeline). Fix = re-run, no code change.
  - Docling finds NOTHING       → Docling genuinely fails on these PDFs (scanned,
    image tables, exotic layout). Fix = change extraction approach.

Usage:
  python3 scripts/extraction/diagnose_tables.py 10.1016/j.jcat.2007.04.006 ...
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PDF_ROOTS = [ROOT / "pdfs", ROOT / "topics/mta/pdfs",
             ROOT / "topics/co2a/pdfs", ROOT / "topics/shared/pdfs"]


def find_pdf(doi: str) -> Path | None:
    slug = doi.replace("/", "_")
    for r in PDF_ROOTS:
        p = r / f"{slug}.pdf"
        if p.exists():
            return p
    for r in PDF_ROOTS:
        if r.exists():
            hits = list(r.glob(f"{slug}*.pdf"))
            if hits:
                return hits[0]
    return None


def diagnose(doi: str, converter) -> dict:
    pdf = find_pdf(doi)
    if not pdf:
        return {"doi": doi, "pdf": None, "error": "PDF not found"}
    try:
        result = converter.convert(pdf)
        doc = result.document
    except Exception as e:
        return {"doi": doi, "pdf": str(pdf), "error": f"convert failed: {e}"}

    tables = []
    for tbl in doc.tables:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = tbl.export_to_dataframe()
            if df is not None and not df.empty:
                tables.append(df)
        except Exception as e:
            tables.append(f"export error: {e}")

    md = doc.export_to_markdown()
    # crude markdown-pipe-table count as a cross-check
    md_table_lines = sum(1 for ln in md.split("\n")
                         if ln.count("|") >= 3)
    return {
        "doi": doi, "pdf": str(pdf.name),
        "n_tables": len([t for t in tables if not isinstance(t, str)]),
        "tables": tables,
        "md_len": len(md),
        "md_pipe_rows": md_table_lines,
    }


def main() -> None:
    dois = sys.argv[1:]
    if not dois:
        raise SystemExit("pass one or more DOIs")
    print(f"Loading Docling … ({len(dois)} papers to check)\n")
    from docling.document_converter import DocumentConverter
    converter = DocumentConverter()

    for doi in dois:
        r = diagnose(doi, converter)
        print("=" * 64)
        print(f"DOI: {r['doi']}  ({r.get('pdf')})")
        if r.get("error"):
            print(f"  ERROR: {r['error']}")
            continue
        print(f"  Docling tables: {r['n_tables']}  | "
              f"markdown len: {r['md_len']}  | "
              f"md pipe-rows: {r['md_pipe_rows']}")
        for i, t in enumerate(r["tables"]):
            if isinstance(t, str):
                print(f"    table[{i}] {t}")
            else:
                cols = list(t.columns)
                print(f"    table[{i}] shape={t.shape}  cols={cols[:6]}"
                      + (" …" if len(cols) > 6 else ""))
                # first data row preview
                if len(t):
                    row0 = [str(x)[:14] for x in t.iloc[0].tolist()[:6]]
                    print(f"               row0={row0}")
    print("=" * 64)
    print("Read: many tables found → DB just never ran v2 on these (re-run).")
    print("      zero tables found → Docling fails on these PDFs (change approach).")


if __name__ == "__main__":
    main()

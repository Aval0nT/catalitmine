"""
ingest_tables.py — Docling table extraction → db.table_rows (no LLM).

The table-centric pipeline needs NO LLM: Docling extracts tables, this script
stores them raw, and build_catalyst_records.py joins them. So recovering tables
for papers that the DB never captured costs only Docling CPU time.

For each DOI: locate the PDF, run Docling, write every table as raw rows into
db.table_rows (columns_json = header list, row_json = one data row). Idempotent
per DOI (existing rows for that DOI's tables from this tool are replaced).

Usage:
  python3 scripts/extraction/ingest_tables.py 10.1016/j.jcat.2007.04.006 ...
  python3 scripts/extraction/ingest_tables.py --from-no-tables --limit 8
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB   = ROOT / "db" / "catalysis.db"
PDF_ROOTS = [ROOT / "pdfs", ROOT / "topics/mta/pdfs",
             ROOT / "topics/co2a/pdfs", ROOT / "topics/shared/pdfs"]
LLM_TAG = "docling-tableformer"   # marks rows produced by this tool


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


def paper_type(conn: sqlite3.Connection, doi: str) -> str | None:
    cur = conn.execute("SELECT paper_type FROM papers WHERE doi=?", (doi,))
    r = cur.fetchone()
    return r[0] if r else None


def no_table_dois(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute("SELECT DISTINCT source_review_doi FROM table_rows")
    with_tables = {r[0] for r in cur.fetchall()}
    cur = conn.execute("SELECT doi FROM papers")
    return [d for (d,) in cur.fetchall() if d not in with_tables]


def extract_tables(pdf: Path, converter):
    """Return list of (caption, headers, rows, page)."""
    result = converter.convert(pdf)
    doc = result.document
    out = []
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
        headers = [str(c) for c in df.columns]
        rows = [[("" if v is None else str(v)) for v in row]
                for row in df.itertuples(index=False, name=None)]
        # caption
        caption = ""
        try:
            caption = tbl.caption_text(doc) or ""
        except Exception:
            pass
        if not caption:
            caption = f"Table {ti}"
        # page
        page = None
        try:
            if tbl.prov:
                page = tbl.prov[0].page_no
        except Exception:
            pass
        out.append((ti, caption, headers, rows, page))
    return out


def store(conn: sqlite3.Connection, doi: str, ptype: str | None, tables) -> int:
    slug = doi.replace("/", "_")
    # idempotent: clear prior rows from THIS tool for this paper
    conn.execute("DELETE FROM table_rows WHERE source_review_doi=? AND llm_model=?",
                 (doi, LLM_TAG))
    primary = doi if ptype != "review" else None
    n = 0
    for ti, caption, headers, rows, page in tables:
        cols_j = json.dumps(headers, ensure_ascii=False)
        for j, row in enumerate(rows, 1):
            row_id = f"{slug}::tbl{ti}::r{j:03d}"
            conn.execute(
                "INSERT OR REPLACE INTO table_rows VALUES (?,?,?,?,?,?,?,?,?)",
                (row_id, doi, primary, str(ti), caption, cols_j,
                 json.dumps(row, ensure_ascii=False), page, LLM_TAG))
            n += 1
    conn.commit()
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Docling tables → db.table_rows (no LLM)")
    ap.add_argument("dois", nargs="*", help="DOIs to ingest")
    ap.add_argument("--from-no-tables", action="store_true",
                    help="Ingest papers in DB that currently have no tables")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    dois = list(args.dois)
    if args.from_no_tables:
        dois += no_table_dois(conn)
    if args.limit:
        dois = dois[:args.limit]
    if not dois:
        raise SystemExit("no DOIs (pass DOIs or --from-no-tables)")

    print(f"Loading Docling … ({len(dois)} papers)\n")
    from docling.document_converter import DocumentConverter
    converter = DocumentConverter()

    grand = 0
    for i, doi in enumerate(dois, 1):
        pdf = find_pdf(doi)
        if not pdf:
            print(f"[{i}/{len(dois)}] {doi}  — PDF not found, skip")
            continue
        try:
            tables = extract_tables(pdf, converter)
        except Exception as e:
            print(f"[{i}/{len(dois)}] {doi}  — convert failed: {e}")
            continue
        ptype = paper_type(conn, doi)
        n = store(conn, doi, ptype, tables)
        grand += n
        print(f"[{i}/{len(dois)}] {doi}  — {len(tables)} tables, {n} rows  "
              f"({ptype or '?'})")
    conn.close()
    print(f"\nDone — {grand} table rows ingested across {len(dois)} papers.")


if __name__ == "__main__":
    main()

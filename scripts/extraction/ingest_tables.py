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


_SI_PAT = ("si", "supporting", "supp", "supplementary", "supplement", "esi")

def _is_si_name(name: str) -> bool:
    low = name.lower()
    return any(tag in low for tag in _SI_PAT)

def find_pdf(doi: str) -> Path | None:
    slug = doi.replace("/", "_")
    for r in PDF_ROOTS:
        p = r / f"{slug}.pdf"
        if p.exists():
            return p
    # glob, but skip SI files so the main PDF wins
    for r in PDF_ROOTS:
        if r.exists():
            hits = [h for h in r.glob(f"{slug}*.pdf") if not _is_si_name(h.name)]
            if hits:
                return hits[0]
    return None

def find_si_pdfs(doi: str) -> list[Path]:
    """Locate Supporting-Information files (PDF or DOCX) the user saved under
    the naming convention <slug>_SI.<ext>, either next to the main PDF or in a
    `SI/` subfolder. Docling reads both PDF and DOCX."""
    slug = doi.replace("/", "_")
    dirs = []
    for r in PDF_ROOTS:
        dirs += [r, r / "SI"]
    out: list[Path] = []
    for r in dirs:
        if not r.exists():
            continue
        for ext in ("pdf", "docx"):
            out += list(r.glob(f"{slug}_SI.{ext}"))
            # also accept publisher-style SI names sitting in a SI/ folder
            if r.name == "SI":
                out += [h for h in r.glob(f"{slug}*.{ext}") if _is_si_name(h.name)]
    return sorted(set(out))


def paper_type(conn: sqlite3.Connection, doi: str) -> str | None:
    cur = conn.execute("SELECT paper_type FROM papers WHERE doi=?", (doi,))
    r = cur.fetchone()
    return r[0] if r else None


def no_table_dois(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute("SELECT DISTINCT source_review_doi FROM table_rows")
    with_tables = {r[0] for r in cur.fetchall()}
    cur = conn.execute("SELECT doi FROM papers")
    return [d for (d,) in cur.fetchall() if d not in with_tables]


def extract_tables(pdf: Path, converter, *, is_si: bool = False,
                   si_prefix: str = "S"):
    """Return list of (table_number, caption, headers, rows, page).

    SI tables are numbered S1, S2, … and captioned with an [SI] prefix so they
    stay traceable to the supplement. When a paper has SEVERAL SI files, each
    file gets its own prefix (S, S2-, S3-, …) so numbering never collides
    across files — colliding table numbers produce colliding row_ids."""
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
        if is_si:
            caption = f"[SI] {caption}"
        # page
        page = None
        try:
            if tbl.prov:
                page = tbl.prov[0].page_no
        except Exception:
            pass
        tnum = f"{si_prefix}{ti}" if is_si else str(ti)
        out.append((tnum, caption, headers, rows, page))
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
            # tool-namespaced: build_db's vision import uses its own namespace,
            # so the two writers can never REPLACE each other's rows
            row_id = f"{slug}::docling::tbl{ti}::r{j:03d}"
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
        # Supporting Information (if the user downloaded it alongside)
        si_pdfs = find_si_pdfs(doi)
        si_tables = []
        for k, si in enumerate(si_pdfs, 1):
            prefix = "S" if k == 1 else f"S{k}-"
            try:
                si_tables += extract_tables(si, converter, is_si=True,
                                            si_prefix=prefix)
            except Exception as e:
                print(f"        [SI convert failed: {si.name}: {e}]")
        all_tables = tables + si_tables
        ptype = paper_type(conn, doi)
        n = store(conn, doi, ptype, all_tables)
        grand += n
        si_note = f" (+{len(si_tables)} SI)" if si_pdfs else ""
        print(f"[{i}/{len(dois)}] {doi}  — {len(tables)} tables{si_note}, "
              f"{n} rows  ({ptype or '?'})")
    conn.close()
    print(f"\nDone — {grand} table rows ingested across {len(dois)} papers.")


if __name__ == "__main__":
    main()

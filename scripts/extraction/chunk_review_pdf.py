"""
Stage A — PDF Chunking

Extracts text from a PDF, splits into paragraph-level chunks with
high-value scoring. Reads from topics/{topic}/pdfs/, writes to data/01_chunks/.

Usage:
  # Single PDF by DOI slug
  python3 scripts/extraction/chunk_review_pdf.py --doi 10.1021_acs.chemrev.9b00723 --topic mta

  # All PDFs in a topic folder
  python3 scripts/extraction/chunk_review_pdf.py --topic mta --all

  # All topics at once
  python3 scripts/extraction/chunk_review_pdf.py --all
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pdfplumber

ROOT       = Path(__file__).resolve().parents[2]
TOPICS_DIR = ROOT / "topics"
CHUNKS_DIR = ROOT / "data" / "01_chunks"
RAW_DIR    = ROOT / "data" / "00_raw"

HIGH_VALUE_PATTERNS = [
    r'\bet al\.', r'\breported\b', r'\bfound\b', r'\bobserved\b',
    r'\bshowed\b', r'\bsuggested\b', r'\bproposed\b',
    r'\bselectivity\b', r'\byield\b', r'\bconversion\b',
    r'\bmechanism\b', r'\bdeactivation\b', r'\bcoke\b',
    r'\bpromoter?\b', r'\bsupport\b',
    r'\baromatization\b', r'\baromatic\b', r'\bBTX\b',
    r'\bZSM-5\b', r'\bzeolite\b', r'\bHZSM\b',
    r'\bmethanol\b', r'\bMTA\b', r'\bMTH\b',
    r'\bCO2\b', r'\bhydrogenation\b', r'\bRWGS\b',
    r'\bGa\b', r'\bZn\b', r'\bCu\b', r'\bMo\b', r'\bCo\b',
    r'\bMPa\b', r'\b°C\b', r'\bGHSV\b',
    r'%\s*(selectivity|conversion|yield)',
    r'\[[0-9,–\- ]+\]',
]


def normalize(text: str) -> str:
    text = text.replace('(cid:0)', '-').replace('(cid:1)', '').replace('\u0000', '')
    return re.sub(r'\s+', ' ', text).strip()


MAX_CHUNK_CHARS = 1800  # split long chunks into sentence-level pieces


def _split_by_sentences(text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
    """Split a long text block into sentence-level chunks (~max_chars each)."""
    sentence_end = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9\[])')
    sentences = sentence_end.split(text)
    chunks: List[str] = []
    buf = ''
    for s in sentences:
        if len(buf) + len(s) > max_chars and buf:
            chunks.append(buf.strip())
            buf = s
        else:
            buf = (buf + ' ' + s).strip() if buf else s
    if buf:
        chunks.append(buf.strip())
    return chunks


def split_paragraphs(page_text: str) -> List[str]:
    lines = [line.strip() for line in page_text.splitlines()]
    paras: List[str] = []
    buff: List[str] = []
    for line in lines:
        if not line:
            if buff:
                paras.append(' '.join(buff))
                buff = []
            continue
        buff.append(line)
    if buff:
        paras.append(' '.join(buff))

    result: List[str] = []
    for p in paras:
        p = normalize(p)
        if not p:
            continue
        if len(p) > MAX_CHUNK_CHARS:
            # Two-column PDF: page text merged → split by sentences
            result.extend(_split_by_sentences(p))
        else:
            result.append(p)
    return result


def score_high_value(text: str) -> int:
    return sum(1 for p in HIGH_VALUE_PATTERNS if re.search(p, text, re.I))


def infer_section(text: str) -> Optional[str]:
    if re.match(r'^(\d+(?:\.\d+)*\.?\s+)\S', text) and len(text) < 120:
        return text
    return None


def slug_to_doi(doi_slug: str) -> str:
    """10.1021_acs.chemrev.9b00723 → 10.1021/acs.chemrev.9b00723"""
    return re.sub(r'^(10\.\d{4})_', r'\1/', doi_slug)


def process_pdf(pdf_path: Path, topic: str) -> None:
    doi_slug = pdf_path.stem
    doi      = slug_to_doi(doi_slug)

    out_chunks = CHUNKS_DIR / f"{doi_slug}.chunks.jsonl"
    out_raw    = RAW_DIR    / f"{doi_slug}.txt"

    if out_chunks.exists():
        print(f"  [skip] already chunked: {doi_slug}")
        return

    print(f"  → {doi_slug}  (topic={topic})")
    records: List[Dict[str, Any]] = []
    raw_pages: List[str] = []
    current_section: Optional[str] = None

    with pdfplumber.open(str(pdf_path)) as doc:
        for page_num, page in enumerate(doc.pages, start=1):
            text = page.extract_text() or ''
            raw_pages.append(text)
            for idx, para in enumerate(split_paragraphs(text), start=1):
                maybe_section = infer_section(para)
                if maybe_section:
                    current_section = maybe_section
                score = score_high_value(para)
                records.append({
                    'chunk_id':         f'{doi_slug}::p{page_num:03d}::c{idx:02d}',
                    'source_doi':       doi,
                    'doi_slug':         doi_slug,
                    'topic':            topic,
                    'page':             page_num,
                    'section':          current_section,
                    'text':             para,
                    'high_value_score': score,
                    'is_high_value':    score >= 3,
                })

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_raw.write_text('\n\n--- PAGE BREAK ---\n\n'.join(raw_pages), encoding='utf-8')

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    with out_chunks.open('w', encoding='utf-8') as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    hv = sum(1 for r in records if r['is_high_value'])
    print(f"     chunks={len(records)}  high_value={hv}  → {out_chunks.name}")


def get_pdfs(topic: Optional[str], doi_slug: Optional[str]) -> List[tuple]:
    results = []
    topics = [topic] if topic else [d.name for d in TOPICS_DIR.iterdir() if d.is_dir()]
    for t in topics:
        pdf_dir = TOPICS_DIR / t / 'pdfs'
        if not pdf_dir.exists():
            continue
        pdfs = sorted(pdf_dir.glob('*.pdf'))
        if doi_slug:
            pdfs = [p for p in pdfs if p.stem == doi_slug]
        results.extend((p, t) for p in pdfs)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage A: PDF → chunks")
    parser.add_argument('--topic', default=None, choices=['mta', 'co2a', 'shared'])
    parser.add_argument('--doi',   default=None, help="Sanitised DOI slug")
    parser.add_argument('--all',   action='store_true', help="Process all PDFs")
    args = parser.parse_args()

    if not args.all and not args.doi:
        parser.error("Specify --doi <slug> or --all")

    pdfs = get_pdfs(args.topic, args.doi)
    if not pdfs:
        print("No PDFs found.")
        return

    print(f"Processing {len(pdfs)} PDF(s)...")
    for pdf_path, topic in pdfs:
        process_pdf(pdf_path, topic)
    print("\nDone.")


if __name__ == '__main__':
    main()

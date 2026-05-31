"""
Extract reference list from PDF pages via Claude Vision OCR.

Used for PDFs where pdfplumber text extraction produces garbled output
(e.g. two-column layouts where reference entries are merged with body text).

Renders each reference page as a PNG image and asks Claude Vision to
return a structured {ref_number: citation_text} mapping.

Output: data/03_evidence/<doi_slug>.ref_lookup.json
        (merged with existing ref_lookup if already present)

Usage:
  python3 scripts/analysis/extract_ref_lookup_vision.py \\
      --doi 10.1016_j.chempr.2021.02.024 --topic mta --pages 31-34
  python3 scripts/analysis/extract_ref_lookup_vision.py \\
      --doi 10.1016_j.chempr.2021.02.024 --topic mta --pages 31-34 --dry-run
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

import pdfplumber

ROOT       = Path(__file__).resolve().parents[2]
TOPICS_DIR = ROOT / "topics"
OUT_DIR    = ROOT / "data" / "03_evidence"
MODEL      = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are a scientific reference list extractor.

Your task: extract every reference entry from the image of a journal paper's reference page.

Rules:
- Return a JSON object mapping reference number (as string) to citation text.
- Include: authors, abbreviated title (first 8 words is enough), journal name, volume, pages, year.
- OMIT full DOI URLs and long URLs — they bloat the output. Year + journal + pages is sufficient.
- Reference numbers may appear as:
    "59." or "59 ." (dot format, Nature/RSC/Wiley)
    "(52)" or "(52) " (bracket format, ACS journals)
    "127." followed by text on the same or next line (Elsevier)
- For two-column layouts: each column may contain separate reference entries — extract ALL of them.
- If a reference spans two lines, join them into one string.
- Do NOT include figure captions, section headers, or non-reference text.
- If a number is ambiguous (e.g. appears as part of a journal volume), skip it.
- Be concise: keep each value under 200 characters.

Return format — a single JSON object, nothing else:
{
  "52": "Fisher, I. A.; Bell, A. T. In-Situ Infrared Study of Methanol Synthesis. J. Catal. 1997, 172, 222.",
  "53": "Nakamura, J.; Uchijima, T. ... J. Catal. 1990, 120, 274.",
  ...
}"""


def page_to_base64(pdf_path: Path, page_num: int, resolution: int = 180) -> str:
    with pdfplumber.open(str(pdf_path)) as doc:
        page = doc.pages[page_num - 1]
        img = page.to_image(resolution=resolution)
        buf = io.BytesIO()
        img.original.save(buf, format="PNG")
        return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


def extract_refs_from_page(client, img_b64: str, page_num: int) -> Dict[str, str]:
    import anthropic as _anthropic

    last_exc = None
    for attempt in range(3):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=8192,
                system=[{"type": "text", "text": SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": img_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                f"Extract all reference entries from this page (page {page_num}). "
                                "Return only the JSON object."
                            ),
                        },
                    ],
                }],
            )
            break
        except (_anthropic.InternalServerError, _anthropic.APIStatusError) as exc:
            last_exc = exc
            status = getattr(exc, "status_code", 0)
            if status in (529, 500) and attempt < 2:
                wait = 2 ** attempt * 5
                print(f"   ⏳ {status} — retry {attempt+1}/3 in {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    else:
        raise last_exc

    # Extract JSON from response text
    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError as e:
        print(f"   ⚠ JSON parse error on p{page_num}: {e}", file=sys.stderr)
        print(f"   Raw output: {raw[:200]}", file=sys.stderr)
        return {}


def parse_page_range(page_range: str) -> List[int]:
    """Parse '31-34' or '31,32,33' into list of ints."""
    pages = []
    for part in page_range.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-")
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return pages


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract reference list via Claude Vision OCR"
    )
    parser.add_argument("--doi",   required=True, help="Sanitised DOI slug")
    parser.add_argument("--topic", required=True, choices=["mta", "co2a", "shared"])
    parser.add_argument("--pages", required=True,
                        help="Page range, e.g. '31-34' or '31,32,33,34'")
    parser.add_argument("--dry-run", action="store_true",
                        help="Render pages and show count only, no API calls")
    args = parser.parse_args()

    pdf_path = TOPICS_DIR / args.topic / "pdfs" / f"{args.doi}.pdf"
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    pages = parse_page_range(args.pages)
    print(f"PDF  : {pdf_path.name}")
    print(f"Pages: {pages}")

    if args.dry_run:
        print("[DRY RUN] Would send these pages to Claude Vision.")
        return

    # Load API key
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    all_refs: Dict[str, str] = {}

    for page_num in pages:
        print(f"  [p{page_num:02d}] Rendering...", end="", flush=True)
        img_b64 = page_to_base64(pdf_path, page_num)
        print(f" calling Vision...", end="", flush=True)
        refs = extract_refs_from_page(client, img_b64, page_num)
        all_refs.update(refs)
        print(f" {len(refs)} refs extracted")
        time.sleep(1)

    print(f"\nTotal refs extracted: {len(all_refs)}")
    if all_refs:
        sample = sorted(all_refs.keys(), key=lambda x: int(x) if x.isdigit() else 999)[:5]
        for k in sample:
            print(f"  [{k}] {all_refs[k][:80]}")

    # Merge with existing ref_lookup if present
    out_path = OUT_DIR / f"{args.doi}.ref_lookup.json"
    existing: Dict[str, str] = {}
    if out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        print(f"\nMerging with existing {len(existing)} entries...")

    merged = {**existing, **all_refs}
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"Saved: {out_path.name}  ({len(merged)} total entries)")


if __name__ == "__main__":
    main()

"""
extract_figures.py — dump figure images from a paper PDF (for chart→data tests).

Uses Docling's picture extraction to crop figure regions to PNGs, so we can feed
real catalysis performance plots to a chart-digitisation tool (Branch A test).

Usage:
  python3 scripts/extraction/extract_figures.py --doi 10.1021/acscatal.5b00192
  python3 scripts/extraction/extract_figures.py --pdf path/to/file.pdf --out figures/charts
"""
from __future__ import annotations

import argparse
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


def extract(pdf: Path, out_dir: Path, scale: float = 2.0) -> int:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.base_models import InputFormat

    opts = PdfPipelineOptions()
    opts.images_scale = scale
    opts.generate_picture_images = True          # keep cropped figure bitmaps
    conv = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})

    result = conv.convert(pdf)
    doc = result.document
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = pdf.stem
    n = 0
    for i, pic in enumerate(doc.pictures, 1):
        img = None
        try:
            img = pic.get_image(doc)             # PIL.Image in docling 2.x
        except Exception:
            img = getattr(getattr(pic, "image", None), "pil_image", None)
        if img is None:
            continue
        page = ""
        try:
            if pic.prov:
                page = f"_p{pic.prov[0].page_no}"
        except Exception:
            pass
        dest = out_dir / f"{stem}_fig{i:02d}{page}.png"
        img.save(dest)
        n += 1
        print(f"  saved {dest.name}  ({img.width}x{img.height})")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract figure images from a paper PDF")
    ap.add_argument("--doi", help="DOI (resolved to a PDF in the topic folders)")
    ap.add_argument("--pdf", help="Direct path to a PDF")
    ap.add_argument("--out", default=str(ROOT / "figures" / "charts"),
                    help="Output folder for figure PNGs")
    ap.add_argument("--scale", type=float, default=2.0, help="Render scale (DPI factor)")
    args = ap.parse_args()

    pdf = Path(args.pdf) if args.pdf else (find_pdf(args.doi) if args.doi else None)
    if not pdf or not pdf.exists():
        raise SystemExit("PDF not found — pass a valid --doi or --pdf")

    print(f"Extracting figures from {pdf.name} …")
    n = extract(pdf, Path(args.out), scale=args.scale)
    print(f"\nDone — {n} figure images → {args.out}")


if __name__ == "__main__":
    main()

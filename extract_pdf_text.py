"""Extract text from PDFs in a folder using pypdf."""

from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", default=".", help="Folder containing PDFs")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Write one UTF-8 .txt file per PDF into this directory; otherwise print to stdout",
    )
    parser.add_argument("--recursive", action="store_true", help="Search subfolders too")
    args = parser.parse_args()

    folder = Path(args.folder).expanduser().resolve()
    if folder.is_file() and folder.suffix.lower() == ".pdf":
        pdfs = [folder]
    elif folder.is_dir():
        pdfs = sorted(folder.rglob("*.pdf") if args.recursive else folder.glob("*.pdf"))
    else:
        parser.error(f"Not a PDF file or directory: {folder}")
    if not pdfs:
        parser.error(f"No PDF files found in {folder}")

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    for pdf_path in pdfs:
        pages = PdfReader(pdf_path).pages
        text = "\n\n".join(
            f"--- Page {page_number} ---\n{page.extract_text() or ''}"
            for page_number, page in enumerate(pages, start=1)
        )
        if args.output_dir:
            output_path = args.output_dir / f"{pdf_path.stem}.txt"
            output_path.write_text(text + "\n", encoding="utf-8")
            print(f"{pdf_path.name}: {len(pages)} pages -> {output_path}")
        else:
            print(f"\n===== {pdf_path.name} ({len(pages)} pages) =====\n{text}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

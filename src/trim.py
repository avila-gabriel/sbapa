"""
trim.py - PDF trimming utilities for SBAPA

Provides functions to:
  • Get total pages of a PDF
  • Trim a PDF given a start/end page range
  • Write the trimmed copy into a target folder
"""

from pathlib import Path
from typing import Optional

from PyPDF2 import PdfReader, PdfWriter


def get_num_pages(pdf_path: Path) -> int:
    """
    Return the total number of pages in the given PDF.
    """
    reader = PdfReader(str(pdf_path))
    return len(reader.pages)


def trim_pdf(
    pdf_path: Path,
    output_dir: Path,
    start_page: int = 1,
    end_page: Optional[int] = None,
    prefix: str = "trimmed_",
) -> Path:
    """
    Trim the PDF at `pdf_path`, keeping pages from `start_page` to `end_page` (inclusive).

    • output_dir: folder where the new PDF will be written (will be created if needed).
    • start_page: 1-based index of the first page to keep.
    • end_page: 1-based index of the last page to keep; if None, defaults to the last page.
    • prefix: filename prefix for the trimmed file.

    Returns the Path to the trimmed PDF.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(pdf_path))
    total = len(reader.pages)
    if end_page is None or end_page > total:
        end_page = total

    # Validate
    if not (1 <= start_page <= end_page <= total):
        raise ValueError(
            f"Invalid range: start={start_page}, end={end_page}, total={total}"
        )

    writer = PdfWriter()
    for pg in range(start_page - 1, end_page):
        writer.add_page(reader.pages[pg])

    out_name = prefix + pdf_path.name
    out_path = output_dir / out_name
    with open(out_path, "wb") as f:
        writer.write(f)

    return out_path

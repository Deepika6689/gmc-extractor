"""
PDF Extraction Layer
=====================
GMC policy PDFs from different insurers arrive as either:
  (a) digitally generated text PDFs (most common — schedules, annexures), or
  (b) scanned/image-only PDFs (older renewal letters, signed endorsements).

This module normalizes both into a single plain-text representation per
document, page-tagged, so the LLM extraction layer never has to care which
path was used.

Strategy:
  1. Try native text extraction with pdfplumber (fast, preserves layout well
     enough for regex/LLM use, and also pulls out actual `Table` objects
     which we flatten into markdown-ish rows — this matters a lot for GMC
     docs because room-rent / waiting-period info is almost always tabular).
  2. If a page yields near-zero text (a scanned page), fall back to OCR via
     pytesseract on a rasterized version of that page only (keeps the
     pipeline fast — we don't OCR pages that don't need it).
"""

from __future__ import annotations
import io
from dataclasses import dataclass, field
from typing import List

import fitz  # PyMuPDF — used for fast rasterization when OCR fallback is needed
import pdfplumber
import pytesseract
from PIL import Image

MIN_CHARS_TO_SKIP_OCR = 40  # a page with fewer real chars than this is treated as "scanned"


@dataclass
class PageContent:
    page_number: int
    text: str
    tables_md: List[str] = field(default_factory=list)
    was_ocr: bool = False


@dataclass
class DocumentContent:
    filename: str
    pages: List[PageContent]

    @property
    def full_text(self) -> str:
        """Flattened, page-tagged text — this is what gets sent to the LLM."""
        chunks = []
        for p in self.pages:
            chunks.append(f"\n===== PAGE {p.page_number} =====\n")
            chunks.append(p.text)
            for t in p.tables_md:
                chunks.append("\n[TABLE]\n" + t + "\n[/TABLE]\n")
        return "\n".join(chunks)

    @property
    def ocr_page_count(self) -> int:
        return sum(1 for p in self.pages if p.was_ocr)


def _table_to_markdown(table: List[List[str]]) -> str:
    if not table:
        return ""
    rows = [[(cell or "").strip().replace("\n", " ") for cell in row] for row in table]
    header = rows[0]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _ocr_page(pdf_path: str, page_index: int, dpi: int = 300) -> str:
    """Rasterize a single page with PyMuPDF and OCR it with tesseract."""
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_index)
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    doc.close()
    return pytesseract.image_to_string(img)


def extract_document(pdf_path: str) -> DocumentContent:
    pages: List[PageContent] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            was_ocr = False

            if len(text.strip()) < MIN_CHARS_TO_SKIP_OCR:
                # Likely a scanned page — fall back to OCR
                try:
                    ocr_text = _ocr_page(pdf_path, i)
                    if len(ocr_text.strip()) > len(text.strip()):
                        text = ocr_text
                        was_ocr = True
                except Exception as e:  # pragma: no cover - OCR is best-effort
                    text = text + f"\n[OCR fallback failed: {e}]"

            tables_md = []
            try:
                for tbl in page.extract_tables():
                    md = _table_to_markdown(tbl)
                    if md:
                        tables_md.append(md)
            except Exception:
                pass  # table extraction is a bonus, not critical path

            pages.append(PageContent(page_number=i + 1, text=text, tables_md=tables_md, was_ocr=was_ocr))

    return DocumentContent(filename=pdf_path, pages=pages)

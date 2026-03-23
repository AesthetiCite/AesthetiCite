from __future__ import annotations
import pdfplumber
from typing import List, Tuple

def extract_pages_from_pdf(pdf_path: str) -> List[Tuple[int, str]]:
    """
    Returns a list of (page_number_1_based, text).
    """
    pages: List[Tuple[int, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            txt = page.extract_text() or ""
            txt = txt.strip()
            if txt:
                pages.append((i + 1, txt))
    return pages

def extract_text_from_pdf(pdf_path: str) -> str:
    pages = extract_pages_from_pdf(pdf_path)
    return "\n\n".join([t for _, t in pages])

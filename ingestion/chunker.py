from __future__ import annotations
import re
from typing import List, Tuple
from app.core.config import settings

MIN_CHUNK_CHARS = 200  # allow shorter chunks for dosage tables, warnings, etc.

# Regex to split at sentence boundaries
SENTENCE_END_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')

def _split_paragraphs(text: str) -> List[str]:
    raw = text.replace("\r", "\n")
    parts = [p.strip() for p in raw.split("\n\n") if p.strip()]
    if not parts:
        return [" ".join(text.split())]
    return parts

def _split_sentences(text: str) -> List[str]:
    """Split text into sentences for finer-grained chunking."""
    sentences = SENTENCE_END_RE.split(text)
    return [s.strip() for s in sentences if s.strip()]

def _extract_section_header(text: str) -> str | None:
    """Extract section headers like 'Methods:', 'Results:', 'Discussion:'"""
    lines = text.strip().split('\n')
    if lines:
        first_line = lines[0].strip()
        if len(first_line) < 50 and (first_line.endswith(':') or first_line.isupper()):
            return first_line
    return None

def chunk_text_with_page(page_no: int, text: str) -> List[Tuple[str, str]]:
    """
    Paragraph-aware chunking within a page.
    Produces fewer junk chunks; keeps p{page}-c{idx} labels.
    """
    paras = _split_paragraphs(text)
    out: List[Tuple[str, str]] = []
    buf = ""

    size = settings.CHUNK_SIZE_CHARS
    overlap = settings.CHUNK_OVERLAP_CHARS
    idx = 0

    def flush():
        nonlocal buf, idx
        chunk = " ".join(buf.split()).strip()
        if len(chunk) >= MIN_CHUNK_CHARS:
            out.append((f"p{page_no}-c{idx}", chunk))
            idx += 1
        buf = ""

    for p in paras:
        if buf and len(buf) + len(p) + 2 > size:
            flush()
            if out and overlap > 0:
                prev = out[-1][1]
                buf = prev[-overlap:] + "\n\n" + p
            else:
                buf = p
        else:
            buf = (buf + "\n\n" + p) if buf else p

    if buf:
        flush()

    return out

def chunk_text(text: str) -> List[Tuple[str, str]]:
    """
    Paragraph-aware chunking for text without page info.
    Returns list of (section_label, chunk_text).
    """
    paras = _split_paragraphs(text)
    out: List[Tuple[str, str]] = []
    buf = ""

    size = settings.CHUNK_SIZE_CHARS
    overlap = settings.CHUNK_OVERLAP_CHARS
    idx = 0

    def flush():
        nonlocal buf, idx
        chunk = " ".join(buf.split()).strip()
        if len(chunk) >= MIN_CHUNK_CHARS:
            out.append((f"chunk_{idx}", chunk))
            idx += 1
        buf = ""

    for p in paras:
        if buf and len(buf) + len(p) + 2 > size:
            flush()
            if out and overlap > 0:
                prev = out[-1][1]
                buf = prev[-overlap:] + "\n\n" + p
            else:
                buf = p
        else:
            buf = (buf + "\n\n" + p) if buf else p

    if buf:
        flush()

    return out

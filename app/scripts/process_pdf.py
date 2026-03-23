#!/usr/bin/env python3
"""
Lightweight script to extract PDF text, chunk it, and insert into pgvector DB.
Uses pdftotext CLI (poppler) instead of PyMuPDF for minimal memory usage.
Embeddings are done separately by the server process.

Usage: python3 app/scripts/process_pdf.py <record_id>
Outputs JSON result to stdout.
"""
import os
import sys
import re
import json
import uuid
import pathlib
import subprocess  # nosec B404

DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", "data"))
PDF_DIR = DATA_DIR / "pdfs"
META_DIR = DATA_DIR / "meta"

MAX_CHARS_PER_CHUNK = 2400
CHUNK_OVERLAP_CHARS = 250
MIN_CHUNK_CHARS = 350


def normalize_whitespace(s):
    s = s.replace("\x00", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def extract_pdf_text(pdf_path):
    result = subprocess.run(  # nosec
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {result.stderr[:200]}")
    return normalize_whitespace(result.stdout)


def chunk_text(text):
    text = normalize_whitespace(text)
    if len(text) <= MAX_CHARS_PER_CHUNK:
        return [text] if len(text) >= MIN_CHUNK_CHARS else []

    paras = text.split("\n\n")
    chunks = []
    buf = []
    buf_len = 0

    def flush():
        nonlocal buf, buf_len
        if not buf:
            return
        c = "\n\n".join(buf).strip()
        if c:
            chunks.append(c)
        buf = []
        buf_len = 0

    for p in paras:
        p = p.strip()
        if not p:
            continue
        if len(p) > MAX_CHARS_PER_CHUNK:
            flush()
            start = 0
            while start < len(p):
                end = min(len(p), start + MAX_CHARS_PER_CHUNK)
                chunks.append(p[start:end].strip())
                start = max(0, end - CHUNK_OVERLAP_CHARS)
            continue
        if buf_len + len(p) + 2 <= MAX_CHARS_PER_CHUNK:
            buf.append(p)
            buf_len += len(p) + 2
        else:
            flush()
            buf.append(p)
            buf_len = len(p) + 2

    flush()

    if CHUNK_OVERLAP_CHARS > 0 and len(chunks) > 1:
        with_overlap = []
        prev_tail = ""
        for c in chunks:
            c2 = (prev_tail + "\n\n" + c).strip() if prev_tail else c
            with_overlap.append(c2)
            prev_tail = c[-CHUNK_OVERLAP_CHARS:]
        chunks = with_overlap

    return [c for c in chunks if len(c) >= MIN_CHUNK_CHARS]


def guess_document_type(meta):
    title = (meta.get("title") or "").lower()
    if any(kw in title for kw in ["guideline", "consensus", "recommendation", "position statement"]):
        return "guideline"
    if any(kw in title for kw in ["randomized", "randomised", "rct", "controlled trial"]):
        return "rct"
    if any(kw in title for kw in ["meta-analysis", "systematic review"]):
        return "systematic_review"
    if any(kw in title for kw in ["review", "overview"]):
        return "review"
    if any(kw in title for kw in ["case report", "case series"]):
        return "case_report"
    return "journal_article"


def guess_domain(meta):
    text = f"{meta.get('title', '')} {meta.get('journal', '')} {meta.get('abstract', '')}".lower()
    if any(kw in text for kw in ["aesthetic", "cosmetic", "filler", "botox", "botulinum", "injectable", "hyaluronic"]):
        return "aesthetic_medicine"
    if any(kw in text for kw in ["dermatol", "skin", "acne", "psoriasis", "eczema"]):
        return "dermatology"
    if any(kw in text for kw in ["plastic surg", "reconstruct"]):
        return "plastic_surgery"
    if any(kw in text for kw in ["laser", "ipl", "radiofrequency", "energy-based", "energy based"]):
        return "energy_devices"
    return "general_medicine"


def output_result(data):
    sys.stdout.write(json.dumps(data))
    sys.stdout.flush()


def main():
    if len(sys.argv) < 2:
        output_result({"error": "Usage: process_pdf.py <record_id>"})
        sys.exit(1)

    record_id = sys.argv[1]
    meta_path = META_DIR / f"{record_id}.json"
    pdf_path = PDF_DIR / f"{record_id}.pdf"

    if not meta_path.exists():
        output_result({"error": "record_id not found"})
        sys.exit(1)
    if not pdf_path.exists():
        output_result({"error": "No PDF found"})
        sys.exit(1)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    doi = meta.get("doi", "")
    title = meta.get("title") or f"DOI:{doi}"
    journal = meta.get("journal")
    year = meta.get("year")
    publisher_url = meta.get("publisher_url")

    try:
        text = extract_pdf_text(pdf_path)
    except Exception as e:
        output_result({"error": f"PDF extraction failed: {str(e)}"})
        sys.exit(1)

    if len(text) < 200:
        output_result({"error": f"PDF text too short ({len(text)} chars)"})
        sys.exit(1)

    chunks_text = chunk_text(text)
    del text

    if not chunks_text:
        output_result({"error": "No meaningful chunks extracted"})
        sys.exit(1)

    doc_type = guess_document_type(meta)
    domain = guess_domain(meta)
    doc_id = uuid.UUID(record_id)

    import psycopg
    db_url = os.environ.get("DATABASE_URL", "")
    conn = psycopg.connect(db_url)
    try:
        cur = conn.cursor()

        cur.execute("SELECT id FROM documents WHERE id = %s", (str(doc_id),))
        existing = cur.fetchone()

        if existing:
            cur.execute("DELETE FROM chunks WHERE document_id = %s", (str(doc_id),))
            cur.execute("""
                UPDATE documents SET title=%s, document_type=%s, domain=%s, year=%s,
                       organization_or_journal=%s, url=%s, updated_at=NOW()
                WHERE id=%s
            """, (title, doc_type, domain, year, journal, publisher_url, str(doc_id)))
        else:
            source_id = f"doi:{doi}" if doi else f"ingest:{record_id}"
            cur.execute("""
                INSERT INTO documents (id, source_id, title, authors, organization_or_journal,
                    year, document_type, domain, version, status, url, file_path, created_at, updated_at)
                VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, NULL, 'active', %s, %s, NOW(), NOW())
            """, (str(doc_id), source_id, title, journal, year, doc_type, domain,
                  publisher_url, str(pdf_path)))

        for i, ct in enumerate(chunks_text):
            chunk_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO chunks (id, document_id, chunk_index, text, page_or_section,
                    evidence_level, embedding, created_at)
                VALUES (%s, %s, %s, %s, NULL, NULL, NULL, NOW())
            """, (chunk_id, str(doc_id), i, ct))

        conn.commit()
    except Exception as e:
        conn.rollback()
        output_result({"error": f"Database error: {str(e)}"})
        sys.exit(1)
    finally:
        conn.close()

    output_result({
        "ok": True,
        "record_id": record_id,
        "document_id": str(doc_id),
        "title": title,
        "chunks_created": len(chunks_text),
        "chunks_embedded": 0,
        "document_type": doc_type,
        "domain": domain,
        "needs_embedding": True,
    })


if __name__ == "__main__":
    main()

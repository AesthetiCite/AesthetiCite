"""
Tiny ingestion script (PI / Guidelines → embeddings → HNSW) for sub-second retrieval.

What it does
- Walks a folder of documents (PDF/TXT/MD/HTML)
- Extracts text (PDF via PyMuPDF)
- Chunks with overlap (good recall)
- Embeds chunks once with OpenAI
- Builds a cosine HNSW index (hnswlib)
- Saves:
    - hnsw.bin        (vector index)
    - hnsw_meta.json  (chunk metadata + text)

How to run (Replit / local)
  pip install openai hnswlib pymupdf beautifulsoup4 lxml tiktoken

  export OPENAI_API_KEY="..."
  export OPENAI_EMBED_MODEL="text-embedding-3-small"   # 1536 dims
  export EMBED_DIM="1536"
  python ingest_hnsw.py --in ./docs/pi_guidelines --out ./index

Then in your API server:
- Load index from ./index/hnsw.bin
- Load meta from ./index/hnsw_meta.json
- HNSW search returns chunk metas (incl. text) immediately

Notes
- This script is intentionally "tiny" and robust, not fancy.
- It supports incremental ingestion via a content hash (skips unchanged chunks).
"""

from __future__ import annotations

import os
import re
import json
import time
import glob
import math
import argparse
import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import hnswlib
from bs4 import BeautifulSoup
from openai import OpenAI

try:
    import tiktoken
except Exception:
    tiktoken = None


DEFAULT_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1536"))
HNSW_M = int(os.getenv("HNSW_M", "16"))
HNSW_EF_CONSTRUCTION = int(os.getenv("HNSW_EF_CONSTRUCTION", "200"))
HNSW_EF = int(os.getenv("HNSW_EF", "128"))

MAX_CHARS_PER_CHUNK = int(os.getenv("MAX_CHARS_PER_CHUNK", "2400"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "250"))
MIN_CHUNK_CHARS = int(os.getenv("MIN_CHUNK_CHARS", "350"))

EMBED_QPS = float(os.getenv("EMBED_QPS", "8.0"))
_last_embed_call = 0.0

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()

def normalize_whitespace(s: str) -> str:
    s = s.replace("\x00", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def guess_source_type(path: str) -> str:
    low = path.lower()
    if "prescribing" in low or "pi" in low or "package insert" in low:
        return "pi"
    if "guideline" in low or "consensus" in low or "recommendation" in low:
        return "guideline"
    return "other"

def _rate_limit(qps: float):
    global _last_embed_call
    if qps <= 0:
        return
    min_interval = 1.0 / qps
    now = time.time()
    wait = (_last_embed_call + min_interval) - now
    if wait > 0:
        time.sleep(wait)
    _last_embed_call = time.time()

def embed(text: str, model: str = DEFAULT_EMBED_MODEL, dim: int = EMBED_DIM) -> List[float]:
    text = (text or "").strip()
    if not text:
        return [0.0] * dim
    _rate_limit(EMBED_QPS)
    resp = client.embeddings.create(model=model, input=text)
    vec = resp.data[0].embedding
    if len(vec) != dim:
        raise RuntimeError(f"Embedding dim mismatch: got {len(vec)} but EMBED_DIM={dim}.")
    return vec


def read_pdf(path: str) -> str:
    doc = fitz.open(path)
    parts = []
    for i in range(len(doc)):
        page = doc[i]
        parts.append(page.get_text("text"))
    return normalize_whitespace("\n".join(parts))

def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return normalize_whitespace(f.read())

def read_html(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    return normalize_whitespace(text)

def load_document(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return read_pdf(path)
    if ext in (".txt", ".md"):
        return read_text(path)
    if ext in (".html", ".htm"):
        return read_html(path)
    return read_text(path)


def chunk_text(text: str, max_chars: int, overlap_chars: int) -> List[str]:
    text = normalize_whitespace(text)
    if len(text) <= max_chars:
        return [text]

    paras = text.split("\n\n")
    chunks: List[str] = []
    buf: List[str] = []
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
        if len(p) > max_chars:
            flush()
            start = 0
            while start < len(p):
                end = min(len(p), start + max_chars)
                chunks.append(p[start:end].strip())
                start = max(0, end - overlap_chars)
            continue

        if buf_len + len(p) + 2 <= max_chars:
            buf.append(p)
            buf_len += len(p) + 2
        else:
            flush()
            buf.append(p)
            buf_len = len(p) + 2

    flush()

    if overlap_chars > 0 and len(chunks) > 1:
        with_overlap = []
        prev_tail = ""
        for c in chunks:
            c2 = (prev_tail + "\n\n" + c).strip() if prev_tail else c
            with_overlap.append(c2)
            prev_tail = c[-overlap_chars:]
        chunks = with_overlap

    chunks = [c for c in chunks if len(c) >= MIN_CHUNK_CHARS]
    return chunks


def load_existing_meta(meta_path: str) -> Dict[str, dict]:
    if not os.path.exists(meta_path):
        return {}
    with open(meta_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("by_hash", {}) or {}

def save_meta(meta_path: str, by_hash: Dict[str, dict], id_to_hash: Dict[int, str], doc_stats: dict):
    payload = {
        "created_at": int(time.time()),
        "embed_model": DEFAULT_EMBED_MODEL,
        "embed_dim": EMBED_DIM,
        "by_hash": by_hash,
        "id_to_hash": {str(k): v for k, v in id_to_hash.items()},
        "doc_stats": doc_stats,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

def build_or_load_hnsw(index_path: str, max_elements: int) -> hnswlib.Index:
    idx = hnswlib.Index(space="cosine", dim=EMBED_DIM)
    if os.path.exists(index_path):
        idx.load_index(index_path)
        idx.set_ef(HNSW_EF)
        return idx
    idx.init_index(max_elements=max_elements, ef_construction=HNSW_EF_CONSTRUCTION, M=HNSW_M)
    idx.set_ef(HNSW_EF)
    return idx


def ingest_folder(
    in_dir: str,
    out_dir: str,
    max_elements: int = 200000,
):
    os.makedirs(out_dir, exist_ok=True)
    index_path = os.path.join(out_dir, "hnsw.bin")
    meta_path = os.path.join(out_dir, "hnsw_meta.json")

    existing_by_hash = load_existing_meta(meta_path)

    by_hash: Dict[str, dict] = dict(existing_by_hash)
    new_count = 0
    updated_docs = 0
    total_docs = 0

    files = []
    for ext in ("pdf", "txt", "md", "html", "htm"):
        files.extend(glob.glob(os.path.join(in_dir, f"**/*.{ext}"), recursive=True))
    files = sorted(set(files))

    if not files:
        raise RuntimeError(f"No documents found under {in_dir}")

    for path in files:
        total_docs += 1
        try:
            text = load_document(path)
        except Exception as e:
            print(f"[WARN] Failed to read: {path} ({e})")
            continue

        if len(text) < 500:
            print(f"[SKIP] Too short: {path}")
            continue

        chunks = chunk_text(text, MAX_CHARS_PER_CHUNK, CHUNK_OVERLAP_CHARS)
        if not chunks:
            print(f"[SKIP] No chunks: {path}")
            continue

        updated_docs += 1
        source_type = guess_source_type(path)
        title = os.path.basename(path)

        for i, ch in enumerate(chunks):
            content_hash = sha256_text(f"{path}\n---\n{i}\n---\n{ch}")
            if content_hash in by_hash:
                continue
            by_hash[content_hash] = {
                "source_path": path,
                "title": title,
                "chunk_index": i,
                "text": ch,
                "source_type": source_type,
                "year": None,
                "doi": None,
                "url": None,
            }
            new_count += 1

    print(f"\nDocs scanned: {total_docs}")
    print(f"Docs parsed:  {updated_docs}")
    print(f"Chunks total: {len(by_hash)} (new this run: {new_count})")

    idx = hnswlib.Index(space="cosine", dim=EMBED_DIM)
    idx.init_index(max_elements=max_elements, ef_construction=HNSW_EF_CONSTRUCTION, M=HNSW_M)
    idx.set_ef(HNSW_EF)

    id_to_hash: Dict[int, str] = {}
    hashes = list(by_hash.keys())

    print("\nEmbedding + indexing...")
    for label, h in enumerate(hashes):
        meta = by_hash[h]
        vec = embed(meta["text"])
        idx.add_items([vec], [label])
        id_to_hash[label] = h
        if (label + 1) % 200 == 0:
            print(f"  indexed {label + 1}/{len(hashes)}")

    idx.save_index(index_path)

    doc_stats = {
        "input_dir": in_dir,
        "files_found": len(files),
        "docs_parsed": updated_docs,
        "chunks_indexed": len(hashes),
    }
    save_meta(meta_path, by_hash, id_to_hash, doc_stats)

    print("\n Done.")
    print(f"Index: {index_path}")
    print(f"Meta:  {meta_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_dir", required=True, help="Folder containing PI/guidelines (PDF/TXT/MD/HTML)")
    ap.add_argument("--out", dest="out_dir", required=True, help="Output folder for hnsw.bin + hnsw_meta.json")
    ap.add_argument("--max", dest="max_elements", type=int, default=200000, help="Max vectors in HNSW index")
    args = ap.parse_args()

    ingest_folder(args.in_dir, args.out_dir, max_elements=args.max_elements)

import os
import re
import json
import uuid
import asyncio
import pathlib
import logging
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

import httpx
import aiofiles
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel, Field

from app.core.admin_auth import require_admin
from app.rag.embedder import embed_text, embed_texts_batch
from app.db.session import SessionLocal
from app.db.models import Document, Chunk
from app.engine.improvements import pubmed_summary, infer_pubtype_from_pubmed_summary, upsert_doc_meta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])

DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", "data"))
PDF_DIR = DATA_DIR / "pdfs"
META_DIR = DATA_DIR / "meta"
INDEX_FILE = DATA_DIR / "index.json"

MAX_PDF_SIZE = 50 * 1024 * 1024

for d in [DATA_DIR, PDF_DIR, META_DIR]:
    d.mkdir(parents=True, exist_ok=True)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _validate_record_id(record_id: str) -> str:
    if not _UUID_RE.match(record_id):
        raise HTTPException(status_code=400, detail="Invalid record_id format (must be UUID)")
    return record_id


def _load_index() -> List[Dict[str, Any]]:
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    return []


def _save_index(items: List[Dict[str, Any]]) -> None:
    INDEX_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def _normalize_doi(doi: str) -> str:
    doi = doi.strip()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = doi.replace("doi:", "").strip()
    return doi


def _is_valid_doi(doi: str) -> bool:
    return bool(re.match(r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$", doi, re.I))


CROSSREF_API = "https://api.crossref.org/works/"
UNPAYWALL_API = "https://api.unpaywall.org/v2/"
PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL")


async def fetch_crossref(doi: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            CROSSREF_API + doi,
            headers={"User-Agent": "AesthetiCite/1.0 (mailto:support@aestheticite.com)"},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=404, detail="Crossref: DOI not found")
        return r.json().get("message", {})


async def fetch_unpaywall(doi: str) -> Dict[str, Any]:
    if not UNPAYWALL_EMAIL:
        return {"error": "UNPAYWALL_EMAIL not set"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{UNPAYWALL_API}{doi}", params={"email": UNPAYWALL_EMAIL})
        if r.status_code != 200:
            return {"error": f"Unpaywall status {r.status_code}"}
        return r.json()


async def pubmed_find_pmid(doi: str) -> Optional[str]:
    params = {"db": "pubmed", "term": f"{doi}[AID]", "retmode": "json", "retmax": "1"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(PUBMED_SEARCH, params=params)
        if r.status_code != 200:
            return None
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        return ids[0] if ids else None


async def pubmed_fetch_abstract(pmid: str) -> Optional[str]:
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(PUBMED_FETCH, params=params)
        if r.status_code != 200:
            return None
        xml = r.text
    abstracts = re.findall(r"<AbstractText.*?>(.*?)</AbstractText>", xml, flags=re.S)
    if not abstracts:
        return None
    cleaned = []
    for a in abstracts:
        a = re.sub(r"<.*?>", "", a)
        a = a.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        cleaned.append(a.strip())
    return "\n".join([c for c in cleaned if c])


async def download_pdf(url: str, dest_path: pathlib.Path) -> None:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True, max_redirects=5) as client:
        async with client.stream("GET", url) as r:
            if r.status_code != 200:
                raise HTTPException(status_code=400, detail=f"PDF download failed ({r.status_code})")
            ctype = r.headers.get("content-type", "").lower()
            total = 0
            chunks = []
            async for chunk in r.aiter_bytes(1024 * 64):
                total += len(chunk)
                if total > MAX_PDF_SIZE:
                    raise HTTPException(status_code=400, detail=f"PDF exceeds {MAX_PDF_SIZE // (1024*1024)}MB limit")
                chunks.append(chunk)
            content = b"".join(chunks)
            if "pdf" not in ctype and not content.startswith(b"%PDF"):
                raise HTTPException(status_code=400, detail="URL did not return a PDF")
            dest_path.write_bytes(content)


class IngestDOIRequest(BaseModel):
    doi: str = Field(..., description="DOI, e.g., 10.1056/NEJMoa...")
    allow_oa_pdf_download: bool = Field(True, description="If true, downloads OA PDF when available")


class IngestResult(BaseModel):
    ok: bool
    record_id: str
    doi: str
    title: Optional[str] = None
    journal: Optional[str] = None
    year: Optional[int] = None
    abstract: Optional[str] = None
    oa_pdf_downloaded: bool = False
    oa_pdf_url: Optional[str] = None
    publisher_url: Optional[str] = None
    notes: Optional[str] = None


@router.post("/doi", response_model=IngestResult)
async def ingest_doi(req: IngestDOIRequest, _auth=Depends(require_admin)):
    doi = _normalize_doi(req.doi)
    if not _is_valid_doi(doi):
        raise HTTPException(status_code=400, detail="Invalid DOI format")

    idx = _load_index()
    existing = [r for r in idx if r.get("doi") == doi]
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"DOI already ingested as record_id={existing[0]['record_id']}"
        )

    record_id = str(uuid.uuid4())

    crossref = await fetch_crossref(doi)
    title = (crossref.get("title") or [None])[0]
    journal = (crossref.get("container-title") or [None])[0]
    year = None
    if crossref.get("issued", {}).get("date-parts"):
        year = crossref["issued"]["date-parts"][0][0]

    publisher_url = crossref.get("URL")

    abstract = None
    pmid = await pubmed_find_pmid(doi)
    pub_type = None
    if pmid:
        abstract = await pubmed_fetch_abstract(pmid)
        try:
            summ = await pubmed_summary(pmid)
            pub_type = infer_pubtype_from_pubmed_summary(summ)
        except Exception as e:
            logger.warning(f"PubMed summary enrichment failed for PMID {pmid}: {e}")
            pub_type = None

    oa_pdf_url = None
    oa_pdf_downloaded = False
    unpaywall = await fetch_unpaywall(doi)

    if isinstance(unpaywall, dict) and unpaywall.get("best_oa_location"):
        loc = unpaywall["best_oa_location"] or {}
        oa_pdf_url = loc.get("url_for_pdf") or loc.get("url")
        if not publisher_url:
            publisher_url = loc.get("url")

    meta = {
        "record_id": record_id,
        "doi": doi,
        "title": title,
        "journal": journal,
        "year": year,
        "publisher_url": publisher_url,
        "pmid": pmid,
        "abstract": abstract,
        "crossref": crossref,
        "unpaywall": unpaywall,
    }
    meta_path = META_DIR / f"{record_id}.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    notes = None
    if req.allow_oa_pdf_download and oa_pdf_url:
        try:
            pdf_path = PDF_DIR / f"{record_id}.pdf"
            await download_pdf(oa_pdf_url, pdf_path)
            oa_pdf_downloaded = True
        except Exception as e:
            notes = f"OA PDF link found but download failed: {e}"

    idx.append({
        "record_id": record_id,
        "doi": doi,
        "title": title,
        "journal": journal,
        "year": year,
        "publisher_url": publisher_url,
        "has_pdf": oa_pdf_downloaded,
        "meta_file": str(meta_path),
        "pdf_file": str(PDF_DIR / f"{record_id}.pdf") if oa_pdf_downloaded else None,
    })
    _save_index(idx)

    try:
        with SessionLocal() as db_sess:
            upsert_doc_meta(
                db_sess,
                source_id=record_id,
                doi=doi,
                pmid=pmid,
                url=publisher_url,
                title=title,
                journal=journal,
                year=year,
                publication_type=pub_type,
            )
            logger.info(f"Upserted documents_meta for {record_id} (pub_type={pub_type})")
    except Exception as e:
        logger.warning(f"Failed to upsert documents_meta for {record_id}: {e}")

    if not oa_pdf_url:
        notes = (notes or "") + (
            " No OA PDF detected (common for paywalled journals). "
            "You can upload your own PDF via /ingest/upload/pdf/{record_id}."
        )

    return IngestResult(
        ok=True,
        record_id=record_id,
        doi=doi,
        title=title,
        journal=journal,
        year=year,
        abstract=abstract,
        oa_pdf_downloaded=oa_pdf_downloaded,
        oa_pdf_url=oa_pdf_url,
        publisher_url=publisher_url,
        notes=notes.strip() if notes else None,
    )


@router.post("/upload/pdf/{record_id}")
async def upload_pdf(record_id: str, file: UploadFile = File(...), _auth=Depends(require_admin)):
    _validate_record_id(record_id)

    if not (META_DIR / f"{record_id}.json").exists():
        raise HTTPException(status_code=404, detail="record_id not found")

    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Please upload a PDF")

    pdf_path = PDF_DIR / f"{record_id}.pdf"
    total = 0
    async with aiofiles.open(pdf_path, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_PDF_SIZE:
                await out.close()
                pdf_path.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail=f"PDF exceeds {MAX_PDF_SIZE // (1024*1024)}MB limit")
            await out.write(chunk)

    idx = _load_index()
    for it in idx:
        if it.get("record_id") == record_id:
            it["has_pdf"] = True
            it["pdf_file"] = str(pdf_path)
            break
    _save_index(idx)

    return {"ok": True, "record_id": record_id, "saved_to": str(pdf_path)}


@router.get("/records")
def list_records(_auth=Depends(require_admin)):
    return _load_index()


MAX_CHARS_PER_CHUNK = 2400
CHUNK_OVERLAP_CHARS = 250
MIN_CHUNK_CHARS = 350

_embed_pool = ThreadPoolExecutor(max_workers=2)


def _normalize_whitespace(s: str) -> str:
    s = s.replace("\x00", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _extract_pdf_text(pdf_path: pathlib.Path) -> str:
    txt_path = pdf_path.with_suffix(".txt")
    if txt_path.exists():
        return _normalize_whitespace(txt_path.read_text(encoding="utf-8", errors="replace"))
    import fitz
    doc = fitz.open(str(pdf_path))
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    text = "\n\n".join(pages)
    txt_path.write_text(text, encoding="utf-8")
    return _normalize_whitespace(text)


def _chunk_text(text: str) -> List[str]:
    text = _normalize_whitespace(text)
    if len(text) <= MAX_CHARS_PER_CHUNK:
        return [text] if len(text) >= MIN_CHUNK_CHARS else []

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
        if len(p) > MAX_CHARS_PER_CHUNK:
            flush()
            start = 0
            while start < len(p):
                end = min(len(p), start + MAX_CHARS_PER_CHUNK)
                chunk_piece = p[start:end].strip()
                if chunk_piece:
                    chunks.append(chunk_piece)
                if end >= len(p):
                    break
                next_start = end - CHUNK_OVERLAP_CHARS
                if next_start <= start:
                    next_start = start + MAX_CHARS_PER_CHUNK
                start = next_start
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


def _guess_document_type(meta: Dict[str, Any]) -> str:
    title = (meta.get("title") or "").lower()
    journal = (meta.get("journal") or "").lower()
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


def _guess_domain(meta: Dict[str, Any]) -> str:
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


class ProcessResult(BaseModel):
    ok: bool
    record_id: str
    document_id: str
    title: Optional[str] = None
    chunks_created: int = 0
    chunks_embedded: int = 0
    document_type: str = ""
    domain: str = ""
    notes: Optional[str] = None


def _get_rss_mb():
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        return -1
    return -1


def _process_record_sync(record_id: str, skip_embedding: bool = False) -> dict:
    """Extract PDF text, chunk, optionally embed, and store in DB."""
    import gc
    from sqlalchemy import text as sql_text

    logger.info(f"[INGEST] Start processing {record_id}, RSS={_get_rss_mb()}MB")

    meta_path = META_DIR / f"{record_id}.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    doi = meta.get("doi", "")
    title = meta.get("title") or f"DOI:{doi}"
    journal = meta.get("journal")
    year = meta.get("year")
    publisher_url = meta.get("publisher_url")

    pdf_path = PDF_DIR / f"{record_id}.pdf"
    logger.info(f"[INGEST] Before pdftotext, RSS={_get_rss_mb()}MB")
    text = _extract_pdf_text(pdf_path)
    logger.info(f"[INGEST] After pdftotext, text={len(text)} chars, RSS={_get_rss_mb()}MB")

    if len(text) < 200:
        return {"error": f"PDF text too short ({len(text)} chars). May be a scanned/image PDF."}

    logger.info(f"[INGEST] Before chunking, RSS={_get_rss_mb()}MB")
    chunks_text = _chunk_text(text)
    logger.info(f"[INGEST] After chunking, {len(chunks_text)} chunks, RSS={_get_rss_mb()}MB")
    del text
    gc.collect()
    logger.info(f"[INGEST] After GC, RSS={_get_rss_mb()}MB")

    if not chunks_text:
        return {"error": "No meaningful chunks could be extracted from the PDF."}

    doc_type = _guess_document_type(meta)
    domain = _guess_domain(meta)
    doc_id = uuid.UUID(record_id)

    logger.info(f"[INGEST] Before DB session, RSS={_get_rss_mb()}MB")
    db = SessionLocal()
    try:
        existing = db.execute(
            sql_text("SELECT id FROM documents WHERE id = :did"),
            {"did": str(doc_id)}
        ).fetchone()

        if existing:
            db.execute(sql_text("DELETE FROM chunks WHERE document_id = :did"), {"did": str(doc_id)})
            db.execute(sql_text("""
                UPDATE documents SET title=:title, document_type=:dt, domain=:dom, year=:yr,
                       organization_or_journal=:journal, url=:url, updated_at=NOW()
                WHERE id=:did
            """), {"title": title, "dt": doc_type, "dom": domain, "yr": year,
                   "journal": journal, "url": publisher_url, "did": str(doc_id)})
        else:
            source_id = f"doi:{doi}" if doi else f"ingest:{record_id}"
            db.execute(sql_text("""
                INSERT INTO documents (id, source_id, title, authors, organization_or_journal,
                    year, document_type, domain, version, status, url, file_path, created_at, updated_at)
                VALUES (:did, :sid, :title, NULL, :journal, :yr, :dt, :dom, NULL, 'active', :url, :fp, NOW(), NOW())
            """), {"did": str(doc_id), "sid": source_id, "title": title, "journal": journal,
                   "yr": year, "dt": doc_type, "dom": domain, "url": publisher_url,
                   "fp": str(pdf_path)})

        logger.info(f"[INGEST] After doc upsert, RSS={_get_rss_mb()}MB")
        embedded_count = 0
        for i, chunk_text_str in enumerate(chunks_text):
            vec_str = None
            if not skip_embedding:
                try:
                    vec = embed_text(chunk_text_str)
                    vec_str = "[" + ",".join(str(v) for v in vec) + "]"
                    embedded_count += 1
                except Exception as e:
                    logger.warning(f"Embedding failed for chunk {i}: {e}")

            chunk_id = str(uuid.uuid4())
            if vec_str:
                db.execute(sql_text("""
                    INSERT INTO chunks (id, document_id, chunk_index, text, page_or_section,
                        evidence_level, embedding, created_at)
                    VALUES (:cid, :did, :ci, :txt, NULL, NULL, CAST(:emb AS vector), NOW())
                """), {"cid": chunk_id, "did": str(doc_id), "ci": i, "txt": chunk_text_str,
                       "emb": vec_str})
            else:
                db.execute(sql_text("""
                    INSERT INTO chunks (id, document_id, chunk_index, text, page_or_section,
                        evidence_level, embedding, created_at)
                    VALUES (:cid, :did, :ci, :txt, NULL, NULL, NULL, NOW())
                """), {"cid": chunk_id, "did": str(doc_id), "ci": i, "txt": chunk_text_str})

            if (i + 1) % 4 == 0:
                db.flush()
                gc.collect()
                logger.info(f"[INGEST] After chunk {i+1}, RSS={_get_rss_mb()}MB")

        db.commit()
        logger.info(f"Processed {record_id}: {len(chunks_text)} chunks, {embedded_count} embedded")
    except Exception as e:
        db.rollback()
        logger.error(f"DB error processing {record_id}: {e}")
        return {"error": f"Database error: {e}"}
    finally:
        db.close()
        gc.collect()

    idx = _load_index()
    for it in idx:
        if it.get("record_id") == record_id:
            it["processed"] = True
            it["chunks_count"] = len(chunks_text)
            break
    _save_index(idx)

    return {
        "ok": True,
        "record_id": record_id,
        "document_id": str(doc_id),
        "title": title,
        "chunks_created": len(chunks_text),
        "chunks_embedded": embedded_count,
        "document_type": doc_type,
        "domain": domain,
    }



@router.get("/debug/mem")
def debug_mem(step: str = "all", _auth=Depends(require_admin)):
    """Debug endpoint - step by step memory check."""
    import gc
    import sys
    from sqlalchemy import text as sql_text
    steps = []
    steps.append(f"start: RSS={_get_rss_mb()}MB")

    if step in ("all", "read"):
        txt_path = PDF_DIR / "fb9015b3-e97d-4c7b-ac67-723c2fc049f1.txt"
        if txt_path.exists():
            text = txt_path.read_text(encoding="utf-8", errors="replace")
            steps.append(f"read_txt: {len(text)} chars, RSS={_get_rss_mb()}MB")
        else:
            steps.append("txt_file_not_found")
        if step == "read":
            return {"steps": steps, "ok": True}

    if step in ("all", "chunk"):
        txt_path = PDF_DIR / "fb9015b3-e97d-4c7b-ac67-723c2fc049f1.txt"
        text = txt_path.read_text(encoding="utf-8", errors="replace") if txt_path.exists() else ""
        chunks = _chunk_text(text)
        steps.append(f"chunking: {len(chunks)} chunks, RSS={_get_rss_mb()}MB")
        del text; gc.collect()
        if step == "chunk":
            return {"steps": steps, "ok": True}

    if step in ("all", "db"):
        db = SessionLocal()
        try:
            count = db.execute(sql_text("SELECT COUNT(*) FROM documents")).scalar()
            steps.append(f"db_query: {count} docs, RSS={_get_rss_mb()}MB")
        finally:
            db.close()
        if step == "db":
            return {"steps": steps, "ok": True}

    return {"steps": steps, "ok": True}


@router.post("/extract/{record_id}")
def extract_text_endpoint(record_id: str, _auth=Depends(require_admin)):
    """Extract text from uploaded PDF using PyMuPDF (in-process, no fork needed)."""
    _validate_record_id(record_id)
    pdf_path = PDF_DIR / f"{record_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="No PDF found. Upload via /ingest/upload/pdf first.")
    txt_path = pdf_path.with_suffix(".txt")
    if txt_path.exists():
        text = txt_path.read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "record_id": record_id, "chars": len(text), "cached": True}

    text = _extract_pdf_text(pdf_path)
    return {"ok": True, "record_id": record_id, "chars": len(text), "cached": False}


@router.post("/process/{record_id}", response_model=ProcessResult)
def process_record(record_id: str, _auth=Depends(require_admin)):
    _validate_record_id(record_id)

    meta_path = META_DIR / f"{record_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="record_id not found")

    pdf_path = PDF_DIR / f"{record_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(
            status_code=400,
            detail="No PDF found for this record. Upload one via /ingest/upload/pdf/{record_id} first."
        )

    result = _process_record_sync(record_id, True)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return ProcessResult(
        ok=True,
        record_id=result["record_id"],
        document_id=result["document_id"],
        title=result.get("title"),
        chunks_created=result["chunks_created"],
        chunks_embedded=result["chunks_embedded"],
        document_type=result["document_type"],
        domain=result["domain"],
        notes=f"Chunked into pgvector ({result['chunks_created']} chunks). Use POST /ingest/embed/{record_id} to generate embeddings for semantic search.",
    )


def _embed_one_chunk_sync(doc_id_str: str) -> dict:
    """Embed a SINGLE un-embedded chunk for a document. Returns progress."""
    import gc
    from sqlalchemy import text as sql_text

    db = SessionLocal()
    try:
        row = db.execute(sql_text("""
            SELECT id, text FROM chunks
            WHERE document_id = :did AND embedding IS NULL
            ORDER BY chunk_index LIMIT 1
        """), {"did": doc_id_str}).fetchone()

        if not row:
            total = db.execute(sql_text(
                "SELECT COUNT(*) FROM chunks WHERE document_id = :did"
            ), {"did": doc_id_str}).scalar() or 0
            return {"done": True, "embedded_this_call": 0, "remaining": 0, "total": total}

        remaining = db.execute(sql_text(
            "SELECT COUNT(*) FROM chunks WHERE document_id = :did AND embedding IS NULL"
        ), {"did": doc_id_str}).scalar() or 0

        chunk_id, chunk_text = str(row[0]), row[1]
        vec = embed_text(chunk_text)
        vec_str = "[" + ",".join(str(v) for v in vec) + "]"
        db.execute(sql_text(
            "UPDATE chunks SET embedding = CAST(:emb AS vector) WHERE id = :cid"
        ), {"emb": vec_str, "cid": chunk_id})
        db.commit()
        gc.collect()

        return {
            "done": remaining <= 1,
            "embedded_this_call": 1,
            "remaining": max(0, remaining - 1),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Embed error: {e}")
        return {"error": str(e)}
    finally:
        db.close()
        gc.collect()


@router.post("/embed/{record_id}")
def embed_document(record_id: str, _auth=Depends(require_admin)):
    """Embed one un-embedded chunk at a time. Call repeatedly until done=true."""
    _validate_record_id(record_id)

    result = _embed_one_chunk_sync(record_id)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result

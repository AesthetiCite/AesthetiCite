from __future__ import annotations
import os
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, Form, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.core.admin_auth import require_admin
from app.core.limiter import limiter
from app.core.governance import get_governance_logs, get_governance_summary
from app.db.session import get_db
from app.rag.embedder import embed_text
from app.rag.cache import get_cache_stats, cleanup_expired_cache
from app.engine.quality_fusion import get_fusion_cache_stats, clear_fusion_cache
from ingestion.pdf_extract import extract_pages_from_pdf
from ingestion.chunker import chunk_text_with_page
from app.schemas.admin import IngestMetadata

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/documents")
def list_documents(_: bool = Depends(require_admin), db: Session = Depends(get_db), limit: int = 50, offset: int = 0):
    rows = db.execute(text("""
      SELECT source_id, title, year, document_type, domain, status, updated_at
      FROM documents
      ORDER BY updated_at DESC NULLS LAST
      LIMIT :limit OFFSET :offset;
    """), {"limit": int(limit), "offset": int(offset)}).mappings().all()
    return {"ok": True, "documents": [dict(r) for r in rows]}

@router.get("/document/{source_id}")
def inspect_document(source_id: str, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    doc = db.execute(text("""
      SELECT id, source_id, title, authors, organization_or_journal, year, document_type, domain, version, status, url, file_path, updated_at
      FROM documents WHERE source_id = :sid;
    """), {"sid": source_id}).mappings().first()
    if not doc:
        return {"ok": False, "reason": "Not found"}

    chunks = db.execute(text("""
      SELECT chunk_index, page_or_section, LEFT(text, 300) AS preview
      FROM chunks
      WHERE document_id = :doc_id
      ORDER BY chunk_index ASC
      LIMIT 200;
    """), {"doc_id": doc["id"]}).mappings().all()

    return {"ok": True, "document": dict(doc), "chunks_preview": [dict(c) for c in chunks]}

@router.post("/ingest_pdf")
@limiter.limit(settings.RATE_LIMIT_INGEST)
def ingest_pdf(
    request: Request,
    _: bool = Depends(require_admin),
    metadata_json: str = Form(...),
    pdf: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a PDF + metadata JSON string (IngestMetadata schema).
    Stores the PDF, extracts text by page, chunks with page labels, embeds, inserts into documents/chunks.
    """
    meta = IngestMetadata.model_validate_json(metadata_json)

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_id = str(uuid.uuid4())
    filename = (pdf.filename or "upload.pdf").replace("/", "_").replace("\\", "_")
    saved_path = os.path.join(settings.UPLOAD_DIR, f"{file_id}_{filename}")

    with open(saved_path, "wb") as f:
        f.write(pdf.file.read())

    pages = extract_pages_from_pdf(saved_path)
    if not pages:
        return {"ok": False, "reason": "No extractable text found in PDF.", "file_path": saved_path}

    all_chunks = []
    for page_no, page_text in pages:
        all_chunks.extend(chunk_text_with_page(page_no, page_text))

    if not all_chunks:
        return {"ok": False, "reason": "Chunking produced no content.", "file_path": saved_path}

    doc_id = db.execute(text("""
      INSERT INTO documents (source_id, title, authors, organization_or_journal, year, document_type, domain, version, status, url, file_path)
      VALUES (:source_id, :title, :authors, :org, :year, :dtype, :domain, :version, 'active', :url, :file_path)
      ON CONFLICT (source_id) DO UPDATE SET
        title=EXCLUDED.title,
        authors=EXCLUDED.authors,
        organization_or_journal=EXCLUDED.organization_or_journal,
        year=EXCLUDED.year,
        document_type=EXCLUDED.document_type,
        domain=EXCLUDED.domain,
        version=EXCLUDED.version,
        status='active',
        url=EXCLUDED.url,
        file_path=EXCLUDED.file_path,
        updated_at=now()
      RETURNING id;
    """), {
        "source_id": meta.source_id,
        "title": meta.title,
        "authors": meta.authors,
        "org": meta.organization_or_journal,
        "year": meta.year,
        "dtype": meta.document_type,
        "domain": meta.domain,
        "version": meta.version,
        "url": meta.url,
        "file_path": saved_path,
    }).scalar_one()

    db.execute(text("DELETE FROM chunks WHERE document_id = :doc_id;"), {"doc_id": doc_id})

    for idx, (pos, txt) in enumerate(all_chunks):
        vec = embed_text(txt)
        db.execute(text("""
          INSERT INTO chunks (document_id, chunk_index, text, page_or_section, evidence_level, embedding)
          VALUES (:doc_id, :idx, :text, :pos, NULL, :emb);
        """), {
            "doc_id": doc_id,
            "idx": idx,
            "text": txt,
            "pos": pos,
            "emb": str(vec),
        })

    db.execute(text("ANALYZE;"))
    db.commit()

    return {"ok": True, "source_id": meta.source_id, "stored_pdf": saved_path, "chunks_inserted": len(all_chunks)}


@router.get("/cache/stats")
def cache_stats(_: bool = Depends(require_admin)):
    """Get caching statistics for embedding and answer caches."""
    stats = get_cache_stats()
    return {"ok": True, "cache_stats": stats}


@router.post("/benchmark/v2")
def run_benchmark_v2(
    _: bool = Depends(require_admin),
    db: Session = Depends(get_db),
    max_questions: int = 15,
):
    """
    Run benchmark with semantic scoring using control plane.
    Per-category tuning, PI fallback, and selective refusal.
    """
    import json
    import time
    from pathlib import Path
    from app.core.control_plane import answer_with_control_plane, detect_category
    from app.core.improve_pack import embed_cached, cosine, extract_numeric_facts
    from app.core.retrieve_wrapper import make_retrieve_fn
    
    questions_path = Path(__file__).parent.parent / "benchmark" / "questions.json"
    with open(questions_path) as f:
        data = json.load(f)
    
    questions_raw = data.get("questions", [])[:max_questions]
    retrieve_fn = make_retrieve_fn(db)
    
    results = []
    t0 = time.time()
    
    for q in questions_raw:
        start = time.time()
        out = answer_with_control_plane(
            query=q["question"],
            filters={"domain": "aesthetic_medicine"},
            retrieve_chunks=retrieve_fn,
            compact=True,
            enable_cache=False,
        )
        latency_ms = int((time.time() - start) * 1000)
        
        refused = bool(out.get("refused"))
        pred = out.get("answer", "")
        gold = q["gold_answer"]
        
        va = embed_cached(pred[:4000])
        vb = embed_cached(gold[:4000])
        sem = max(0.0, min(1.0, (cosine(va, vb) + 1.0) / 2.0))
        
        gold_nums = set()
        for kw in q.get("expected_keywords", []):
            gold_nums.update(extract_numeric_facts(kw))
        gold_nums.update(extract_numeric_facts(gold))
        pred_nums = set(extract_numeric_facts(pred))
        num_score = len(pred_nums.intersection(gold_nums)) / max(1, len(gold_nums)) if gold_nums else 1.0
        
        allow_refusal = not q.get("must_refuse", False)
        if refused and allow_refusal:
            final = max(sem, 0.75)
            notes = "refusal_credit"
        elif refused and not allow_refusal:
            final = 0.0
            notes = "refused_not_allowed"
        else:
            final = 0.70 * sem + 0.30 * num_score
            notes = ""
        
        results.append({
            "id": q["id"],
            "category": q["category"],
            "refused": refused,
            "latency_ms": latency_ms,
            "semantic_score": round(sem, 3),
            "numeric_score": round(num_score, 3),
            "final_score": round(final, 3),
            "detected_category": out.get("meta", {}).get("category", ""),
            "notes": notes
        })
    
    elapsed_ms = int((time.time() - t0) * 1000)
    avg = sum(r["final_score"] for r in results) / max(1, len(results))
    
    by_cat = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r)
    cat_scores = {c: round(sum(x["final_score"] for x in xs)/len(xs), 3) for c, xs in by_cat.items()}
    
    def grade(s):
        if s >= 0.90: return "A"
        if s >= 0.80: return "B"
        if s >= 0.70: return "C"
        if s >= 0.60: return "D"
        return "F"
    
    return {
        "ok": True,
        "benchmark_version": "v3_control_plane",
        "overall_score": round(avg, 3),
        "grade": grade(avg),
        "total": len(results),
        "refused": sum(1 for r in results if r["refused"]),
        "avg_latency_ms": int(sum(r["latency_ms"] for r in results)/max(1, len(results))),
        "elapsed_ms": elapsed_ms,
        "category_scores": cat_scores,
        "results": results,
    }


@router.post("/cache/cleanup")
def cache_cleanup(_: bool = Depends(require_admin)):
    """Manually trigger cleanup of expired cache entries."""
    cleanup_expired_cache()
    return {"ok": True, "message": "Cache cleanup completed"}


@router.post("/benchmark/usmle")
def run_usmle_benchmark(
    _: bool = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Run USMLE-style medical licensing exam benchmark using MCQ mode.
    Tests against OpenEvidence's 100% USMLE score.
    """
    import json
    from pathlib import Path
    from app.core.mcq_mode import run_mcq_benchmark
    from app.core.retrieve_wrapper import make_retrieve_fn
    
    questions_path = Path(__file__).parent.parent / "benchmark" / "usmle_questions.json"
    with open(questions_path) as f:
        data = json.load(f)
    
    questions = data.get("questions", [])
    retrieve_fn = make_retrieve_fn(db)
    
    result = run_mcq_benchmark(
        questions=questions,
        retrieve_chunks=retrieve_fn,
        filters={"domain": "aesthetic_medicine"},
    )
    
    return {
        "ok": True,
        "benchmark": "USMLE-Style Medical Exam (MCQ Mode)",
        "openevidence_score": 100.0,
        "gap_to_openevidence": round(100.0 - result["accuracy_percent"], 1),
        **result,
    }


def _csv_escape(x) -> str:
    s = "" if x is None else str(x)
    s = s.replace('"', '""')
    return f'"{s}"'


@router.get("/stats/enterprise")
def admin_enterprise_stats(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    """
    Enterprise credibility metrics: active users, conversations, messages, engagement.
    """
    users = db.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
    convs = db.execute(text("SELECT COUNT(*) FROM conversations")).scalar() or 0
    msgs = db.execute(text("SELECT COUNT(*) FROM messages")).scalar() or 0
    last30 = db.execute(text(
        "SELECT COUNT(*) FROM messages WHERE created_at > (now() - interval '30 days')"
    )).scalar() or 0

    top = db.execute(text("""
        SELECT c.id AS conversation_id,
               COALESCE(c.title,'') AS title,
               COUNT(m.id) AS message_count,
               MAX(m.created_at) AS last_activity
        FROM conversations c
        JOIN messages m ON m.conversation_id = c.id
        GROUP BY c.id
        ORDER BY message_count DESC
        LIMIT 10
    """)).mappings().all()

    return {
        "ok": True,
        "counts": {
            "users": int(users),
            "conversations": int(convs),
            "messages": int(msgs),
            "messages_last_30d": int(last30),
        },
        "top_conversations": [dict(r) for r in top],
    }


@router.get("/export/pilot.csv")
def admin_export_pilot_csv(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    """
    CSV export for pilots: per-user usage breakdown.
    """
    per_user = db.execute(text("""
        SELECT u.email,
               COUNT(DISTINCT c.id) AS conversations,
               COUNT(m.id) AS messages,
               SUM(CASE WHEN m.role='user' THEN 1 ELSE 0 END) AS user_turns,
               SUM(CASE WHEN m.role='assistant' THEN 1 ELSE 0 END) AS assistant_turns,
               MAX(m.created_at) AS last_activity
        FROM users u
        LEFT JOIN conversations c ON c.user_id=u.id
        LEFT JOIN messages m ON m.conversation_id=c.id
        GROUP BY u.email
        ORDER BY messages DESC NULLS LAST
    """)).mappings().all()

    lines = []
    header = ["email", "conversations", "messages", "user_turns", "assistant_turns", "last_activity"]
    lines.append(",".join(header))
    for r in per_user:
        lines.append(",".join([
            _csv_escape(r["email"]),
            str(r["conversations"] or 0),
            str(r["messages"] or 0),
            str(r["user_turns"] or 0),
            str(r["assistant_turns"] or 0),
            _csv_escape(r.get("last_activity")),
        ]))

    csv_data = "\n".join(lines) + "\n"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=aestheticite_pilot_export.csv"},
    )


@router.get("/governance-logs")
def admin_governance_logs(
    _: bool = Depends(require_admin),
    limit: int = 100,
    offset: int = 0,
):
    logs = get_governance_logs(limit=int(limit), offset=int(offset))
    summary = get_governance_summary()
    return {"ok": True, "summary": summary, "logs": logs}


@router.get("/cache/fusion")
def admin_fusion_cache_stats(_: bool = Depends(require_admin)):
    return {"ok": True, **get_fusion_cache_stats()}


@router.post("/cache/fusion/clear")
def admin_fusion_cache_clear(_: bool = Depends(require_admin)):
    result = clear_fusion_cache()
    return {"ok": True, **result}

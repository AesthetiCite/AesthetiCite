"""
Seeds the database with 2 demo documents + chunks + embeddings.
Run once after setting DATABASE_URL in .env.

Usage:
  python ingestion/seed_demo.py
"""
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.rag.embedder import embed_text

db_url = settings.DATABASE_URL
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://")

engine = create_engine(db_url, pool_pre_ping=True)

DEMO_DOCS = [
    {
        "source_id": "consensus_demo_2021",
        "title": "Consensus guidance on management of vascular compromise after dermal filler (DEMO)",
        "authors": "Demo Group",
        "organization_or_journal": "Consensus Statement",
        "year": 2021,
        "document_type": "consensus",
        "domain": "aesthetic_medicine",
        "version": "demo",
        "status": "active",
        "chunks": [
            ("p1-c0", "Early recognition and prompt intervention are emphasized; recommendations are consensus-based. Algorithm for emergency management of vascular occlusion."),
            ("p2-c0", "When hyaluronic acid filler is implicated, hyaluronidase is described as a rescue option in consensus guidance; evidence quality may be limited.")
        ],
    },
    {
        "source_id": "review_demo_2020",
        "title": "Review: Hyaluronidase use in filler-related ischemic events (DEMO)",
        "authors": "Demo Author",
        "organization_or_journal": "Dermatologic Review",
        "year": 2020,
        "document_type": "review",
        "domain": "aesthetic_medicine",
        "version": "demo",
        "status": "active",
        "chunks": [
            ("p1-c0", "The evidence base is limited; practice commonly relies on expert consensus and case series. Treatment approach for filler-related ischemic events."),
        ],
    },
]

def upsert_document(conn, d):
    doc_id = conn.execute(text("""
      INSERT INTO documents (source_id, title, authors, organization_or_journal, year, document_type, domain, version, status)
      VALUES (:source_id, :title, :authors, :org, :year, :dtype, :domain, :version, :status)
      ON CONFLICT (source_id) DO UPDATE SET
        title=EXCLUDED.title,
        authors=EXCLUDED.authors,
        organization_or_journal=EXCLUDED.organization_or_journal,
        year=EXCLUDED.year,
        document_type=EXCLUDED.document_type,
        domain=EXCLUDED.domain,
        version=EXCLUDED.version,
        status=EXCLUDED.status,
        updated_at=now()
      RETURNING id;
    """), {
        "source_id": d["source_id"],
        "title": d["title"],
        "authors": d.get("authors"),
        "org": d.get("organization_or_journal"),
        "year": d.get("year"),
        "dtype": d.get("document_type"),
        "domain": d.get("domain"),
        "version": d.get("version"),
        "status": d.get("status", "active"),
    }).scalar_one()
    return doc_id

def insert_chunks(conn, doc_id, chunks):
    conn.execute(text("DELETE FROM chunks WHERE document_id = :doc_id;"), {"doc_id": doc_id})

    for i, (pos, txt) in enumerate(chunks):
        vec = embed_text(txt)
        conn.execute(text("""
          INSERT INTO chunks (document_id, chunk_index, text, page_or_section, evidence_level, embedding)
          VALUES (:doc_id, :idx, :text, :pos, :evidence, :emb);
        """), {
            "doc_id": doc_id,
            "idx": i,
            "text": txt,
            "pos": pos,
            "evidence": None,
            "emb": str(vec),
        })

def main():
    with engine.begin() as conn:
        for d in DEMO_DOCS:
            doc_id = upsert_document(conn, d)
            insert_chunks(conn, doc_id, d["chunks"])
        conn.execute(text("ANALYZE;"))
    print("✅ Seeded demo documents and chunks with REAL 384-dim embeddings.")

if __name__ == "__main__":
    main()

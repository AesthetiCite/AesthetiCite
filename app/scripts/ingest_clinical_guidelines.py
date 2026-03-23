"""
Ingest clinical dosing guidelines and prescribing information into the AesthetiCite knowledge base.
"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from sqlalchemy import text
from app.db.session import SessionLocal
from app.rag.embedder import embed_text

DATA_DIR = Path(__file__).parent.parent / "data"

GUIDELINES_FILES = [
    "clinical_dosing_guidelines.json",
    "clinical_guidelines_cardiology.json",
    "clinical_guidelines_neurology.json",
    "clinical_guidelines_psychiatry.json",
    "clinical_guidelines_infectious.json",
    "clinical_guidelines_emergency.json",
    "clinical_guidelines_endocrinology.json",
    "clinical_guidelines_pediatrics.json",
    "clinical_guidelines_oncology.json",
]

PRESCRIBING_INFO_FILES = [
    "prescribing_info_aesthetic.json",
    "prescribing_info_cardiology.json",
    "prescribing_info_neurology.json",
    "prescribing_info_psychiatry.json",
    "prescribing_info_endocrinology.json",
    "prescribing_info_infectious.json",
    "prescribing_info_emergency.json",
]

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks."""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        
        if end < len(text):
            last_period = chunk.rfind('.')
            last_newline = chunk.rfind('\n')
            break_point = max(last_period, last_newline)
            if break_point > chunk_size // 2:
                chunk = text[start:start + break_point + 1]
                end = start + break_point + 1
        
        chunks.append(chunk.strip())
        start = end - overlap
    
    return [c for c in chunks if c]

def ingest_guidelines():
    """Load and ingest clinical dosing guidelines from all files."""
    print("=" * 60)
    print("AesthetiCite Clinical Guidelines Ingestion - ALL FIELDS")
    print("=" * 60)
    
    all_guidelines = []
    for filename in GUIDELINES_FILES:
        filepath = DATA_DIR / filename
        if filepath.exists():
            with open(filepath, 'r') as f:
                data = json.load(f)
            guidelines = data.get("guidelines", [])
            all_guidelines.extend(guidelines)
            print(f"  Loaded {len(guidelines)} guidelines from {filename}")
        else:
            print(f"  [SKIP] {filename} not found")
    
    guidelines = all_guidelines
    print(f"\nTotal: {len(guidelines)} clinical guidelines to ingest")
    
    ingested = 0
    skipped = 0
    
    with SessionLocal() as db:
        for guideline in guidelines:
            source_id = guideline["source_id"]
            
            existing = db.execute(
                text("SELECT id FROM documents WHERE source_id = :sid"),
                {"sid": source_id}
            ).fetchone()
            
            if existing:
                print(f"  [SKIP] {source_id} already exists")
                skipped += 1
                continue
            
            doc_id = str(uuid.uuid4())
            content = guideline["content"]
            
            db.execute(
                text("""
                    INSERT INTO documents (
                        id, source_id, title, authors, organization_or_journal, 
                        year, document_type, domain, specialty, language, status, created_at
                    )
                    VALUES (
                        :id, :source_id, :title, :authors, :journal,
                        :year, :doc_type, :domain, :specialty, 'english', 'active', :created
                    )
                """),
                {
                    "id": doc_id,
                    "source_id": source_id,
                    "title": guideline["title"],
                    "authors": guideline.get("authors", ""),
                    "journal": guideline.get("journal", "Clinical Practice Guidelines"),
                    "year": guideline.get("year", 2024),
                    "doc_type": guideline.get("document_type", "clinical_guideline"),
                    "domain": guideline.get("domain", "aesthetic_medicine"),
                    "specialty": guideline.get("specialty", "general"),
                    "created": datetime.utcnow()
                }
            )
            
            chunks = chunk_text(content)
            print(f"  [INGEST] {source_id}: {len(chunks)} chunks")
            
            for i, chunk in enumerate(chunks):
                chunk_id = str(uuid.uuid4())
                embedding = embed_text(chunk)
                
                db.execute(
                    text("""
                        INSERT INTO chunks (
                            id, document_id, chunk_index, text, 
                            page_or_section, evidence_level, embedding, created_at
                        )
                        VALUES (
                            :id, :doc_id, :idx, :text,
                            :section, :evidence, :embedding, :created
                        )
                    """),
                    {
                        "id": chunk_id,
                        "doc_id": doc_id,
                        "idx": i,
                        "text": chunk,
                        "section": f"Section {i+1}",
                        "evidence": "I",
                        "embedding": embedding,
                        "created": datetime.utcnow()
                    }
                )
            
            ingested += 1
            db.commit()
    
    print("=" * 60)
    print(f"Ingestion complete: {ingested} ingested, {skipped} skipped")
    print("=" * 60)
    return {"ingested": ingested, "skipped": skipped}


def ingest_prescribing_info():
    """Load and ingest manufacturer prescribing information from all files."""
    print("=" * 60)
    print("AesthetiCite Prescribing Information Ingestion")
    print("=" * 60)
    
    all_docs = []
    for filename in PRESCRIBING_INFO_FILES:
        filepath = DATA_DIR / filename
        if filepath.exists():
            with open(filepath, 'r') as f:
                data = json.load(f)
            docs = data.get("prescribing_info", [])
            all_docs.extend(docs)
            print(f"  Loaded {len(docs)} prescribing info docs from {filename}")
        else:
            print(f"  [SKIP] {filename} not found")
    
    print(f"\nTotal: {len(all_docs)} prescribing info documents to ingest")
    
    ingested = 0
    skipped = 0
    
    with SessionLocal() as db:
        for doc in all_docs:
            source_id = doc["source_id"]
            
            existing = db.execute(
                text("SELECT id FROM documents WHERE source_id = :sid"),
                {"sid": source_id}
            ).fetchone()
            
            if existing:
                print(f"  [SKIP] {source_id} already exists")
                skipped += 1
                continue
            
            doc_id = str(uuid.uuid4())
            content = doc["content"]
            
            db.execute(
                text("""
                    INSERT INTO documents (
                        id, source_id, title, authors, organization_or_journal, 
                        year, document_type, domain, specialty, language, status, created_at
                    )
                    VALUES (
                        :id, :source_id, :title, :authors, :journal,
                        :year, :doc_type, :domain, :specialty, 'english', 'active', :created
                    )
                """),
                {
                    "id": doc_id,
                    "source_id": source_id,
                    "title": doc["title"],
                    "authors": doc.get("authors", ""),
                    "journal": doc.get("journal", "FDA Prescribing Information"),
                    "year": doc.get("year", 2024),
                    "doc_type": "prescribing_information",
                    "domain": doc.get("domain", "medicine"),
                    "specialty": doc.get("specialty", "general"),
                    "created": datetime.utcnow()
                }
            )
            
            chunks = chunk_text(content)
            print(f"  [INGEST] {source_id}: {len(chunks)} chunks")
            
            for i, chunk in enumerate(chunks):
                chunk_id = str(uuid.uuid4())
                embedding = embed_text(chunk)
                
                db.execute(
                    text("""
                        INSERT INTO chunks (
                            id, document_id, chunk_index, text, 
                            page_or_section, evidence_level, embedding, created_at
                        )
                        VALUES (
                            :id, :doc_id, :idx, :text,
                            :section, :evidence, :embedding, :created
                        )
                    """),
                    {
                        "id": chunk_id,
                        "doc_id": doc_id,
                        "idx": i,
                        "text": chunk,
                        "section": f"Section {i+1}",
                        "evidence": "I",
                        "embedding": embedding,
                        "created": datetime.utcnow()
                    }
                )
            
            ingested += 1
            db.commit()
    
    print("=" * 60)
    print(f"Prescribing Info Ingestion: {ingested} ingested, {skipped} skipped")
    print("=" * 60)
    return {"ingested": ingested, "skipped": skipped}


if __name__ == "__main__":
    ingest_guidelines()
    print("\n")
    ingest_prescribing_info()

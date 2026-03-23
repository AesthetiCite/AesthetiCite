"""
Ingest downloaded PMC full-text articles into Veridoc database.
Parses XML for metadata, chunks text, generates embeddings, stores in database.

Usage:
  python ingestion/ingest_pmc.py
"""
import os
import re
from defusedxml import ElementTree as ET
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.rag.embedder import embed_text
from ingestion.chunker import chunk_text

db_url = settings.DATABASE_URL
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://")

engine = create_engine(db_url, pool_pre_ping=True)

PMC_DIR = "data/pmc_fulltext"

def parse_pmc_xml(xml_path: str) -> dict:
    """Extract metadata and text from PMC XML."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Extract metadata from front matter
        front = root.find(".//front")
        
        # Title
        title_elem = root.find(".//article-title")
        title = "".join(title_elem.itertext()).strip() if title_elem is not None else ""
        
        # Journal
        journal_elem = root.find(".//journal-title")
        journal = "".join(journal_elem.itertext()).strip() if journal_elem is not None else ""
        
        # Year
        year_elem = root.find(".//pub-date/year")
        year = year_elem.text.strip() if year_elem is not None else ""
        
        # Authors
        authors = []
        for contrib in root.findall(".//contrib[@contrib-type='author']"):
            surname = contrib.find(".//surname")
            given = contrib.find(".//given-names")
            if surname is not None:
                name = surname.text or ""
                if given is not None and given.text:
                    name = f"{given.text} {name}"
                authors.append(name.strip())
        author_str = ", ".join(authors[:5])
        if len(authors) > 5:
            author_str += " et al."
        
        # PMCID
        pmcid_elem = root.find(".//article-id[@pub-id-type='pmc']")
        pmcid = pmcid_elem.text.strip() if pmcid_elem is not None else ""
        
        # PMID
        pmid_elem = root.find(".//article-id[@pub-id-type='pmid']")
        pmid = pmid_elem.text.strip() if pmid_elem is not None else ""
        
        # Extract body text
        body = root.find(".//body")
        if body is not None:
            body_text = " ".join(body.itertext())
        else:
            body_text = " ".join(root.itertext())
        
        # Clean text
        body_text = re.sub(r'\s+', ' ', body_text).strip()
        
        return {
            "title": title,
            "journal": journal,
            "year": int(year) if year.isdigit() else None,
            "authors": author_str,
            "pmcid": pmcid,
            "pmid": pmid,
            "text": body_text,
        }
    except Exception as e:
        print(f"  Error parsing XML: {e}")
        return None

def upsert_document(conn, meta: dict) -> int:
    """Insert or update document, return document ID."""
    source_id = f"pmc_{meta['pmcid']}" if meta.get('pmcid') else f"pmc_{meta.get('pmid', 'unknown')}"
    
    doc_id = conn.execute(text("""
      INSERT INTO documents (source_id, title, authors, organization_or_journal, year, document_type, domain, version, status, url)
      VALUES (:source_id, :title, :authors, :org, :year, :dtype, :domain, :version, 'active', :url)
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
        updated_at=now()
      RETURNING id;
    """), {
        "source_id": source_id,
        "title": meta.get("title", "Unknown Title"),
        "authors": meta.get("authors", ""),
        "org": meta.get("journal", ""),
        "year": meta.get("year"),
        "dtype": "review",  # Most PMC articles we're ingesting are reviews
        "domain": "aesthetic_medicine",
        "version": "1.0",
        "url": f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{meta.get('pmcid', '')}/" if meta.get('pmcid') else "",
    }).scalar_one()
    
    return doc_id

def insert_chunks(conn, doc_id: int, chunks: list):
    """Delete existing chunks and insert new ones with embeddings."""
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
    xml_files = [f for f in os.listdir(PMC_DIR) if f.endswith('.xml')]
    
    if not xml_files:
        print(f"No XML files found in {PMC_DIR}")
        return
    
    print(f"Found {len(xml_files)} XML files to ingest\n")
    
    ingested = 0
    total_chunks = 0
    
    with engine.begin() as conn:
        for xml_file in sorted(xml_files):
            xml_path = os.path.join(PMC_DIR, xml_file)
            print(f"Processing: {xml_file}")
            
            meta = parse_pmc_xml(xml_path)
            if not meta or not meta.get("text"):
                print(f"  Skipped: No content extracted")
                continue
            
            # Chunk the text
            chunks = chunk_text(meta["text"])
            if not chunks:
                print(f"  Skipped: No chunks generated")
                continue
            
            # Upsert document and insert chunks
            doc_id = upsert_document(conn, meta)
            insert_chunks(conn, doc_id, chunks)
            
            ingested += 1
            total_chunks += len(chunks)
            print(f"  ✓ Ingested: {meta.get('title', 'Unknown')[:60]}...")
            print(f"    {len(chunks)} chunks, {len(meta['text'])//1024} KB text")
        
        # Analyze for query optimization
        conn.execute(text("ANALYZE documents;"))
        conn.execute(text("ANALYZE chunks;"))
    
    print(f"\n{'='*50}")
    print(f"Ingested {ingested}/{len(xml_files)} documents")
    print(f"Total chunks: {total_chunks}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()

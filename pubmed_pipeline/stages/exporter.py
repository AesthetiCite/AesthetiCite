"""
Export module for AesthetiCite retrieval format.
Supports performance hooks for freshness calculation and export shaping.
"""

import re
import json
import gzip
import html
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

class PublicationExporter:
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url, pool_pre_ping=True)
        self.current_year = datetime.now().year
    
    def export_jsonl(
        self,
        output_path: str,
        source_types: Optional[list] = None,
        min_year: Optional[int] = None,
        limit: Optional[int] = None,
        compress: bool = False
    ) -> int:
        query = """
            SELECT pmid, title, abstract, journal, year, doi, 
                   mesh_terms, publication_types, pubmed_url, source_type, quality_rank,
                   authors, language
            FROM publications
            WHERE 1=1
        """
        params = {}
        
        if source_types:
            query += " AND source_type = ANY(:types)"
            params["types"] = source_types
        
        if min_year:
            query += " AND year >= :min_year"
            params["min_year"] = min_year
        
        query += " ORDER BY quality_rank DESC, year DESC"
        
        if limit:
            query += " LIMIT :limit"
            params["limit"] = limit
        
        count = 0
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        opener = gzip.open if compress else open
        mode = 'wt' if compress else 'w'
        
        with self.engine.connect() as conn:
            result = conn.execute(text(query), params)
            
            with opener(output, mode) as f:
                for row in result:
                    freshness_years = max(0, self.current_year - row.year) if row.year else None
                    
                    record = {
                        "id": f"pubmed:{row.pmid}",
                        "pmid": row.pmid,
                        "title": self._normalize_text(row.title or ""),
                        "abstract": self._normalize_text(row.abstract or ""),
                        "year": row.year,
                        "journal": row.journal or "",
                        "doi": row.doi,
                        "authors": row.authors or [],
                        "language": row.language or "eng",
                        "mesh_terms": row.mesh_terms or [],
                        "publication_types": row.publication_types or [],
                        "url": row.pubmed_url or f"https://pubmed.ncbi.nlm.nih.gov/{row.pmid}/",
                        "source": "pubmed",
                        "source_type": row.source_type or "other",
                        "quality_rank": row.quality_rank or 35,
                        "freshness_years": freshness_years,
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
        
        logger.info(f"Exported {count} publications to {output_path}")
        return count
    
    def export_for_aestheticite(self, output_path: str, limit: Optional[int] = None) -> int:
        """Export in AesthetiCite-optimized format for retrieval."""
        query = """
            SELECT pmid, title, abstract, journal, year, doi, 
                   mesh_terms, publication_types, pubmed_url, source_type, quality_rank,
                   pmc_id
            FROM publications
            WHERE (abstract IS NOT NULL AND LENGTH(abstract) > 50) 
               OR LENGTH(title) > 20
            ORDER BY quality_rank DESC, year DESC
        """
        params = {}
        if limit:
            query += " LIMIT :limit"
            params["limit"] = limit
        
        count = 0
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        with self.engine.connect() as conn:
            result = conn.execute(text(query), params)
            
            with open(output, 'w') as f:
                for row in result:
                    title = self._normalize_text(row.title or "")
                    abstract = self._normalize_text(row.abstract or "")
                    text_content = f"{title}\n\n{abstract}" if abstract else title
                    
                    freshness = max(0, self.current_year - row.year) if row.year else None
                    
                    year_bucket = None
                    if row.year:
                        if row.year >= 2020:
                            year_bucket = "recent"
                        elif row.year >= 2010:
                            year_bucket = "modern"
                        elif row.year >= 2000:
                            year_bucket = "established"
                        else:
                            year_bucket = "classic"
                    
                    record = {
                        "id": f"pubmed:{row.pmid}",
                        "text": text_content,
                        "title": title,
                        "year": row.year,
                        "source_type": row.source_type or "other",
                        "url": row.pubmed_url or "",
                        "doi": row.doi or "",
                        "_score": row.quality_rank / 100.0 if row.quality_rank else 0.35,
                        "tier": self._infer_tier(row.source_type, row.quality_rank),
                        "quality_rank": row.quality_rank or 35,
                        "freshness_years": freshness,
                        "year_bucket": year_bucket,
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
        
        logger.info(f"Exported {count} publications for AesthetiCite to {output_path}")
        return count
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text: collapse whitespace, strip HTML."""
        if not text:
            return ""
        text = html.unescape(text)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _infer_tier(self, source_type: str, quality_rank: int) -> str:
        """Infer tier from source type and quality rank."""
        if quality_rank >= 80:
            return "tier1"
        elif quality_rank >= 50:
            return "tier2"
        return "tier3"
    
    def get_stats(self) -> Dict:
        with self.engine.connect() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM publications")).scalar()
            
            by_type = conn.execute(text("""
                SELECT source_type, COUNT(*), 
                       ROUND(AVG(quality_rank), 1) as avg_rank
                FROM publications 
                GROUP BY source_type 
                ORDER BY COUNT(*) DESC
            """)).fetchall()
            
            by_year = conn.execute(text("""
                SELECT year, COUNT(*) 
                FROM publications 
                WHERE year >= 2000
                GROUP BY year 
                ORDER BY year DESC
            """)).fetchall()
            
            top_journals = conn.execute(text("""
                SELECT journal, COUNT(*) 
                FROM publications 
                WHERE journal IS NOT NULL AND journal != ''
                GROUP BY journal 
                ORDER BY COUNT(*) DESC
                LIMIT 20
            """)).fetchall()
            
            top_mesh = conn.execute(text("""
                SELECT unnest(mesh_terms) as term, COUNT(*) 
                FROM publications 
                WHERE mesh_terms IS NOT NULL
                GROUP BY term 
                ORDER BY COUNT(*) DESC
                LIMIT 30
            """)).fetchall()
            
            with_abstract = conn.execute(text("""
                SELECT COUNT(*) FROM publications 
                WHERE abstract IS NOT NULL AND LENGTH(abstract) > 50
            """)).scalar()
        
        return {
            "total_publications": total,
            "with_abstract": with_abstract,
            "by_source_type": [{"type": r[0], "count": r[1], "avg_rank": float(r[2]) if r[2] else 0} for r in by_type],
            "by_year": [{"year": r[0], "count": r[1]} for r in by_year],
            "top_journals": [{"journal": r[0], "count": r[1]} for r in top_journals],
            "top_mesh_terms": [{"term": r[0], "count": r[1]} for r in top_mesh],
        }

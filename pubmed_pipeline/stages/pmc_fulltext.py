"""
Stage 4 (Optional): PMC OA Full-Text Retrieval
================================================
Downloads full-text from PubMed Central Open Access subset ONLY.
This module is toggled OFF by default.

Legal Note:
-----------
This module ONLY downloads content from the PMC Open Access Subset,
which allows text mining and redistribution under various CC licenses.
It does NOT access paywalled or subscription-only content.
"""

import time
import requests
import defusedxml.ElementTree as ET
import logging
import gzip
from pathlib import Path
from typing import List, Dict, Optional, Set
from dataclasses import dataclass

from sqlalchemy import create_engine, text
from pubmed_pipeline.utils.throttle import RateLimiter, retry_with_backoff, ProgressTracker

logger = logging.getLogger(__name__)

PMC_OA_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
EFETCH_PMC_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

@dataclass
class PMCFullText:
    pmc_id: str
    pmid: Optional[str]
    full_text: str
    sections: Dict[str, str]
    license: str

class PMCOAFetcher:
    """
    Fetches full-text from PMC Open Access subset.
    
    IMPORTANT: This ONLY works for OA content. Non-OA PMC articles
    will return empty results, which is the correct behavior.
    """
    
    def __init__(self, db_url: str, rate_limit_qps: float = 3.0, enabled: bool = False):
        """
        Initialize PMC OA fetcher.
        
        Args:
            db_url: Database connection string
            rate_limit_qps: Rate limit for API calls
            enabled: Whether to actually fetch content (default: False)
        """
        self.engine = create_engine(db_url, pool_pre_ping=True)
        self.rate_limiter = RateLimiter(rate_limit_qps)
        self.enabled = enabled
        
        if not enabled:
            logger.info("PMC OA full-text fetching is DISABLED by default")
    
    def get_pmids_with_pmc(self, limit: int = 1000) -> List[tuple]:
        """Get PMIDs that have PMC IDs but no full-text yet."""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT p.pmid, p.pmc_id 
                FROM publications p
                LEFT JOIN pmc_fulltext f ON p.pmc_id = f.pmc_id
                WHERE p.pmc_id IS NOT NULL AND f.pmc_id IS NULL
                LIMIT :limit
            """), {"limit": limit})
            return [(row[0], row[1]) for row in result]
    
    @retry_with_backoff(max_retries=3, base_delay=2.0, exceptions=(requests.RequestException,))
    def check_oa_status(self, pmc_ids: List[str]) -> Dict[str, str]:
        """
        Check which PMC IDs are in the OA subset.
        Returns dict of pmc_id -> license for OA articles.
        """
        if not self.enabled:
            return {}
        
        self.rate_limiter.wait()
        
        oa_articles = {}
        for pmc_id in pmc_ids:
            try:
                clean_id = pmc_id.replace("PMC", "")
                params = {"id": clean_id}
                r = requests.get(PMC_OA_URL, params=params, timeout=30)
                r.raise_for_status()
                
                root = ET.fromstring(r.content)
                record = root.find(".//record")
                if record is not None:
                    license_elem = record.find(".//license")
                    license_text = license_elem.text if license_elem is not None else "OA"
                    oa_articles[pmc_id] = license_text
                
                time.sleep(0.1)
                
            except Exception as e:
                logger.debug(f"PMC {pmc_id} not in OA subset or error: {e}")
        
        return oa_articles
    
    @retry_with_backoff(max_retries=3, base_delay=2.0, exceptions=(requests.RequestException, ET.ParseError))
    def fetch_fulltext(self, pmc_id: str) -> Optional[PMCFullText]:
        """
        Fetch full-text XML from PMC for an OA article.
        """
        if not self.enabled:
            return None
        
        self.rate_limiter.wait()
        
        try:
            clean_id = pmc_id.replace("PMC", "")
            params = {
                "db": "pmc",
                "id": clean_id,
                "retmode": "xml",
            }
            
            r = requests.get(EFETCH_PMC_URL, params=params, timeout=120)
            r.raise_for_status()
            
            return self.parse_pmc_xml(pmc_id, r.content)
            
        except Exception as e:
            logger.error(f"Failed to fetch PMC {pmc_id}: {e}")
            return None
    
    def parse_pmc_xml(self, pmc_id: str, content: bytes) -> Optional[PMCFullText]:
        """Parse PMC XML into structured full-text."""
        try:
            root = ET.fromstring(content)
            article = root.find(".//article")
            if article is None:
                return None
            
            pmid_elem = article.find(".//article-id[@pub-id-type='pmid']")
            pmid = pmid_elem.text if pmid_elem is not None else None
            
            license_elem = article.find(".//license")
            license_text = ""
            if license_elem is not None:
                license_p = license_elem.find(".//license-p")
                if license_p is not None:
                    license_text = "".join(license_p.itertext())
            
            sections = {}
            full_text_parts = []
            
            abstract = article.find(".//abstract")
            if abstract is not None:
                abstract_text = " ".join(p.text or "" for p in abstract.findall(".//p") if p.text)
                if abstract_text:
                    sections["abstract"] = abstract_text
                    full_text_parts.append(f"ABSTRACT: {abstract_text}")
            
            body = article.find(".//body")
            if body is not None:
                for sec in body.findall(".//sec"):
                    title_elem = sec.find("title")
                    title = title_elem.text if title_elem is not None else "Section"
                    
                    paragraphs = []
                    for p in sec.findall(".//p"):
                        text = "".join(p.itertext())
                        if text.strip():
                            paragraphs.append(text.strip())
                    
                    if paragraphs:
                        section_text = " ".join(paragraphs)
                        sections[title.lower()] = section_text
                        full_text_parts.append(f"{title.upper()}: {section_text}")
            
            full_text = "\n\n".join(full_text_parts)
            
            return PMCFullText(
                pmc_id=pmc_id,
                pmid=pmid,
                full_text=full_text,
                sections=sections,
                license=license_text[:100] if license_text else "OA",
            )
            
        except Exception as e:
            logger.error(f"Failed to parse PMC XML for {pmc_id}: {e}")
            return None
    
    def store_fulltext(self, ft: PMCFullText) -> bool:
        """Store full-text in database."""
        try:
            with self.engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO pmc_fulltext (pmc_id, pmid, full_text, sections, license)
                    VALUES (:pmc_id, :pmid, :text, :sections, :license)
                    ON CONFLICT (pmc_id) DO UPDATE SET
                        full_text = EXCLUDED.full_text,
                        sections = EXCLUDED.sections,
                        fetched_at = NOW()
                """), {
                    "pmc_id": ft.pmc_id,
                    "pmid": ft.pmid,
                    "text": ft.full_text,
                    "sections": ft.sections,
                    "license": ft.license,
                })
            return True
        except Exception as e:
            logger.error(f"Failed to store fulltext for {ft.pmc_id}: {e}")
            return False
    
    def run(self, limit: int = 1000, batch_size: int = 50) -> Dict[str, int]:
        """
        Run full-text ingestion for OA articles.
        
        Returns:
            Dict with counts: checked, oa_found, fetched, stored, failed
        """
        if not self.enabled:
            logger.warning("PMC OA fetching is disabled. Set enabled=True to enable.")
            return {"checked": 0, "oa_found": 0, "fetched": 0, "stored": 0, "failed": 0}
        
        articles = self.get_pmids_with_pmc(limit)
        logger.info(f"Found {len(articles)} articles with PMC IDs to check")
        
        stats = {"checked": 0, "oa_found": 0, "fetched": 0, "stored": 0, "failed": 0}
        
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            pmc_ids = [pmc_id for _, pmc_id in batch]
            
            oa_status = self.check_oa_status(pmc_ids)
            stats["checked"] += len(batch)
            stats["oa_found"] += len(oa_status)
            
            for pmc_id, license_text in oa_status.items():
                ft = self.fetch_fulltext(pmc_id)
                if ft:
                    stats["fetched"] += 1
                    if self.store_fulltext(ft):
                        stats["stored"] += 1
                    else:
                        stats["failed"] += 1
                else:
                    stats["failed"] += 1
            
            logger.info(f"Progress: {stats}")
        
        return stats
    
    def get_stats(self) -> Dict:
        """Get statistics about stored full-text."""
        with self.engine.connect() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM pmc_fulltext")).scalar() or 0
            by_license = conn.execute(text("""
                SELECT license, COUNT(*) 
                FROM pmc_fulltext 
                GROUP BY license 
                ORDER BY COUNT(*) DESC
                LIMIT 10
            """)).fetchall()
            avg_length = conn.execute(text("""
                SELECT ROUND(AVG(LENGTH(full_text))) 
                FROM pmc_fulltext
            """)).scalar() or 0
        
        return {
            "total_fulltext": total,
            "by_license": {row[0]: row[1] for row in by_license},
            "avg_text_length": avg_length,
        }


def main():
    """CLI entry point for PMC OA module."""
    import argparse
    from pubmed_pipeline.utils.config import get_db_url
    
    parser = argparse.ArgumentParser(description="PMC OA Full-Text Fetcher")
    parser.add_argument("--enable", action="store_true", help="Enable fetching (disabled by default)")
    parser.add_argument("--limit", type=int, default=100, help="Max articles to process")
    parser.add_argument("--qps", type=float, default=3.0, help="Queries per second")
    parser.add_argument("--stats", action="store_true", help="Show statistics only")
    
    args = parser.parse_args()
    
    db_url = get_db_url()
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return 1
    
    fetcher = PMCOAFetcher(db_url, rate_limit_qps=args.qps, enabled=args.enable)
    
    if args.stats:
        stats = fetcher.get_stats()
        print(f"\nPMC Full-Text Statistics:")
        print(f"  Total: {stats['total_fulltext']}")
        print(f"  Avg length: {stats['avg_text_length']} chars")
        return 0
    
    if not args.enable:
        print("PMC OA fetching is DISABLED by default.")
        print("Use --enable to actually fetch content.")
        print("\nThis module ONLY downloads from PMC Open Access Subset.")
        return 0
    
    result = fetcher.run(limit=args.limit)
    print(f"\nResults: {result}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

"""
Stage 3: Normalization + Storage
=================================
Stores publications in database with deduplication and source type classification.
Uses performance hooks from corpus.yaml for classification and ranking.
"""

import logging
from datetime import datetime
from typing import List, Dict
from sqlalchemy import create_engine, text, update, table, column

from pubmed_pipeline.stages.fetcher import Publication
from pubmed_pipeline.utils.hooks import (
    classify_source_type,
    get_quality_rank,
    QUALITY_RANK,
)

logger = logging.getLogger(__name__)


class PublicationStorage:
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url, pool_pre_ping=True)
    
    def store_batch(self, publications: List[Publication], run_id: int = None) -> Dict:
        stored = 0
        skipped = 0
        failed = 0
        
        with self.engine.begin() as conn:
            for pub in publications:
                try:
                    source_type = classify_source_type(
                        pub.publication_types, 
                        pub.title, 
                        pub.abstract,
                    )
                    quality_rank = get_quality_rank(source_type)
                    pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pub.pmid}/"
                    
                    freshness_years = None
                    if pub.year:
                        freshness_years = max(0, current_year - pub.year)
                    
                    result = conn.execute(text("""
                        INSERT INTO publications 
                        (pmid, title, abstract, journal, year, doi, publication_types, 
                         mesh_terms, authors, language, pmc_id, pubmed_url, source_type, quality_rank)
                        VALUES 
                        (:pmid, :title, :abstract, :journal, :year, :doi, :pub_types,
                         :mesh, :authors, :lang, :pmc, :url, :stype, :qrank)
                        ON CONFLICT (pmid) DO UPDATE SET
                            title = COALESCE(NULLIF(EXCLUDED.title, ''), publications.title),
                            abstract = CASE 
                                WHEN LENGTH(EXCLUDED.abstract) > LENGTH(COALESCE(publications.abstract, '')) 
                                THEN EXCLUDED.abstract 
                                ELSE publications.abstract 
                            END,
                            updated_at = NOW()
                        RETURNING pmid
                    """), {
                        "pmid": pub.pmid,
                        "title": pub.title[:2000] if pub.title else "",
                        "abstract": pub.abstract,
                        "journal": pub.journal[:500] if pub.journal else "",
                        "year": pub.year,
                        "doi": pub.doi[:200] if pub.doi else None,
                        "pub_types": pub.publication_types,
                        "mesh": pub.mesh_terms,
                        "authors": pub.authors,
                        "lang": pub.language,
                        "pmc": pub.pmc_id,
                        "url": pubmed_url,
                        "stype": source_type,
                        "qrank": quality_rank,
                    })
                    
                    if result.fetchone():
                        stored += 1
                    else:
                        skipped += 1
                        
                except Exception as e:
                    logger.error(f"Failed to store PMID {pub.pmid}: {e}")
                    failed += 1
        
        return {"stored": stored, "skipped": skipped, "failed": failed}
    
    def get_existing_pmids(self) -> set:
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT pmid FROM publications"))
            return {row[0] for row in result}
    
    def get_existing_dois(self) -> set:
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT doi FROM publications WHERE doi IS NOT NULL"))
            return {row[0] for row in result}
    
    def count_publications(self) -> Dict:
        with self.engine.connect() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM publications")).scalar()
            by_type = conn.execute(text("""
                SELECT source_type, COUNT(*) 
                FROM publications 
                GROUP BY source_type 
                ORDER BY COUNT(*) DESC
            """)).fetchall()
            by_year = conn.execute(text("""
                SELECT year, COUNT(*) 
                FROM publications 
                WHERE year IS NOT NULL
                GROUP BY year 
                ORDER BY year DESC
                LIMIT 20
            """)).fetchall()
        
        return {
            "total": total,
            "by_source_type": {row[0]: row[1] for row in by_type},
            "by_year": {row[0]: row[1] for row in by_year},
        }


class IngestionRunManager:
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url, pool_pre_ping=True)
    
    def create_run(self, mode: str, config_hash: str, config_snapshot: dict = None) -> int:
        import json
        with self.engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO ingestion_runs (mode, query_plan_hash, config_snapshot)
                VALUES (:mode, :hash, :snapshot)
                RETURNING run_id
            """), {"mode": mode, "hash": config_hash, "snapshot": json.dumps(config_snapshot) if config_snapshot else None})
            return result.scalar()
    
    _ALLOWED_RUN_COLUMNS = frozenset({
        "ended_at", "mode", "query_plan_hash", "config_snapshot",
        "pmids_found", "pmids_fetched", "pmids_stored", "pmids_skipped",
        "pmids_failed", "errors", "status",
    })

    def update_run(self, run_id: int, **kwargs):
        invalid = kwargs.keys() - self._ALLOWED_RUN_COLUMNS
        if invalid:
            raise ValueError(f"Invalid column(s) for ingestion_runs update: {invalid}")
        runs_table = table("ingestion_runs", column("run_id"), *[column(k) for k in kwargs])
        stmt = update(runs_table).where(column("run_id") == run_id).values(**kwargs)
        with self.engine.begin() as conn:
            conn.execute(stmt)
    
    def complete_run(self, run_id: int, counts: Dict):
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE ingestion_runs SET
                    ended_at = NOW(),
                    status = 'completed',
                    pmids_found = :found,
                    pmids_fetched = :fetched,
                    pmids_stored = :stored,
                    pmids_skipped = :skipped,
                    pmids_failed = :failed
                WHERE run_id = :run_id
            """), {
                "run_id": run_id,
                "found": counts.get("found", 0),
                "fetched": counts.get("fetched", 0),
                "stored": counts.get("stored", 0),
                "skipped": counts.get("skipped", 0),
                "failed": counts.get("failed", 0),
            })
    
    def fail_run(self, run_id: int, error: str):
        import json
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE ingestion_runs SET
                    ended_at = NOW(),
                    status = 'failed',
                    errors = :errors
                WHERE run_id = :run_id
            """), {"run_id": run_id, "errors": json.dumps([{"error": error}])})

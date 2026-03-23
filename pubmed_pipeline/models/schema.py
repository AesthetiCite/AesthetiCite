"""
Database schema for PubMed harvesting pipeline.

Tables:
- publications: Core publication metadata
- ingestion_runs: Track each pipeline run
- pmid_queue: Queue for incremental fetching
- pmc_fulltext: Optional full-text storage (OA only)
"""

SCHEMA_SQL = """
-- Publications table: core metadata storage
CREATE TABLE IF NOT EXISTS publications (
    pmid VARCHAR(20) PRIMARY KEY,
    title TEXT,
    abstract TEXT,
    journal VARCHAR(500),
    year INTEGER,
    doi VARCHAR(200),
    publication_types TEXT[],
    mesh_terms TEXT[],
    authors TEXT[],
    language VARCHAR(20),
    pmc_id VARCHAR(20),
    pubmed_url VARCHAR(200),
    source VARCHAR(50) DEFAULT 'pubmed',
    source_type VARCHAR(50),
    quality_rank INTEGER DEFAULT 50,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_publications_year ON publications(year);
CREATE INDEX IF NOT EXISTS idx_publications_doi ON publications(doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_publications_source_type ON publications(source_type);
CREATE INDEX IF NOT EXISTS idx_publications_journal ON publications(journal);

-- Ingestion runs table: track pipeline executions
CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id SERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    mode VARCHAR(50) NOT NULL,
    query_plan_hash VARCHAR(64),
    config_snapshot JSONB,
    pmids_found INTEGER DEFAULT 0,
    pmids_fetched INTEGER DEFAULT 0,
    pmids_stored INTEGER DEFAULT 0,
    pmids_skipped INTEGER DEFAULT 0,
    pmids_failed INTEGER DEFAULT 0,
    errors JSONB DEFAULT '[]'::jsonb,
    status VARCHAR(20) DEFAULT 'running'
);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_status ON ingestion_runs(status);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_started ON ingestion_runs(started_at DESC);

-- PMID queue table: for incremental processing
CREATE TABLE IF NOT EXISTS pmid_queue (
    id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES ingestion_runs(run_id),
    pmid VARCHAR(20) NOT NULL,
    tier VARCHAR(20),
    query_group VARCHAR(100),
    status VARCHAR(20) DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    UNIQUE(run_id, pmid)
);

CREATE INDEX IF NOT EXISTS idx_pmid_queue_status ON pmid_queue(status);
CREATE INDEX IF NOT EXISTS idx_pmid_queue_run ON pmid_queue(run_id);

-- PMC full-text table (optional, OA only)
CREATE TABLE IF NOT EXISTS pmc_fulltext (
    pmc_id VARCHAR(20) PRIMARY KEY,
    pmid VARCHAR(20) REFERENCES publications(pmid),
    full_text TEXT,
    sections JSONB,
    license VARCHAR(100),
    fetched_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pmc_fulltext_pmid ON pmc_fulltext(pmid);

-- Checkpoint table for resume capability
CREATE TABLE IF NOT EXISTS pipeline_checkpoints (
    checkpoint_id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES ingestion_runs(run_id),
    stage VARCHAR(50),
    batch_number INTEGER,
    last_pmid VARCHAR(20),
    checkpoint_data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

def init_schema(engine):
    """Initialize database schema."""
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(SCHEMA_SQL))
    print("Schema initialized successfully.")

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Full-text search index (keyword retrieval)
CREATE INDEX IF NOT EXISTS idx_chunks_fts
ON chunks
USING gin (to_tsvector('english', text));

-- Trigram fuzzy index (helps for names/terms)
CREATE INDEX IF NOT EXISTS idx_chunks_text_trgm
ON chunks
USING gin (text gin_trgm_ops);

-- Helpful filter indexes
CREATE INDEX IF NOT EXISTS idx_documents_status_domain_type_year
ON documents(status, domain, document_type, year);

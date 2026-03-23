# PubMed Harvesting Pipeline for AesthetiCite

A 3-stage pipeline for harvesting biomedical publications from PubMed with incremental updates, deduplication, and filtering.

## Overview

This pipeline:
- Harvests ~1,000,000 biomedical publications (metadata + abstracts) from PubMed
- Optionally harvests open-access full text from PubMed Central (OA subset only)
- Outputs data optimized for retrieval (vector + keyword) for AesthetiCite

## Legal & Compliance Note

**IMPORTANT**: This pipeline ingests bibliographic metadata and abstracts from PubMed. Where full text is ingested, it is limited to open-access sources such as PubMed Central OA content. For paywalled articles, AesthetiCite stores citations and links, not the full text.

### What We Harvest
- Publication metadata (title, authors, journal, year, DOI)
- Abstracts (publicly available via NCBI E-utilities)
- MeSH terms and publication types
- Links to original publications

### What We Do NOT Harvest
- Copyrighted full-text from paywalled journals
- Publisher PDFs without explicit open-access license
- Any content that requires subscription access

### Credible Phrasing

**For Clinicians:**
> "AesthetiCite indexes biomedical evidence from PubMed and prioritizes prescribing information and guidelines for clinical answers. Full-text is used when available via open-access sources; otherwise, we rely on abstracts and citation metadata with links to the original publisher."

**For Investors:**
> "Indexed over 1,000,000 biomedical publication records (metadata + abstracts) and continuously updates new publications. Full-text ingestion is restricted to open-access repositories and licensed sources."

## Installation

```bash
# Ensure DATABASE_URL is set
export DATABASE_URL="postgresql://user:pass@host:port/db"

# Initialize database schema
python -m pubmed_pipeline init
```

## Usage

### 1. Query Planning

Create or use the provided `corpus.yaml` configuration:

```bash
# Run query planning to discover PMIDs
python -m pubmed_pipeline plan --config corpus.yaml --output data/pmids.json
```

### 2. Fetch Publications

```bash
# Fetch all planned PMIDs
python -m pubmed_pipeline fetch --pmids-file data/pmids.json --batch-size 200

# With rate limiting and raw response saving
python -m pubmed_pipeline fetch --pmids-file data/pmids.json --qps 3.0 --save-raw
```

### 3. Incremental Updates

```bash
# Update with publications from last 7 days
python -m pubmed_pipeline incremental --days 7 --config corpus.yaml

# Weekly update (recommended for production)
python -m pubmed_pipeline incremental --days 7
```

### 4. Export for Retrieval

```bash
# Export to JSONL for AesthetiCite
python -m pubmed_pipeline export --format aestheticite --output data/pubmed_export.jsonl

# Export specific source types
python -m pubmed_pipeline export --format jsonl --types guideline,rct,meta_analysis --output data/guidelines.jsonl

# Export with filters
python -m pubmed_pipeline export --format jsonl --min-year 2020 --limit 100000 --output data/recent.jsonl
```

### 5. View Statistics

```bash
python -m pubmed_pipeline stats
```

## Configuration

### corpus.yaml Structure

```yaml
name: "corpus_name"
version: "1.0"
target_total: 1000000

global_filters:
  humans_only: true
  languages: ["eng", "fre"]
  date_range: [2000, 2026]

rate_limit_qps: 3.0
batch_size: 500

query_groups:
  - name: "group_name"
    tier: "tier1"  # tier1, tier2, or tier3
    target_count: 10000
    queries:
      - "search term[Title/Abstract]"
    mesh_terms:
      - "MeSH Term"
    publication_types:
      - "Clinical Trial"
    date_range: [2000, 2026]
    exclude_terms:
      - "mouse[Title/Abstract]"
```

### Tier Strategy

| Tier | Purpose | Target Count |
|------|---------|--------------|
| Tier 1 | High-precision aesthetic core | 50,000 |
| Tier 2 | Adjacent safety & anatomy | 300,000 |
| Tier 3 | Broad biomedical safety net | 650,000 |

## Database Schema

### publications
- `pmid` (PK): PubMed ID
- `title`, `abstract`: Core content
- `journal`, `year`, `doi`: Bibliographic data
- `publication_types`, `mesh_terms`, `authors`: Arrays
- `source_type`: Classified type (guideline, rct, review, etc.)
- `quality_rank`: Priority for retrieval (100=highest)

### ingestion_runs
Tracks each pipeline execution for auditing and resume capability.

### pmid_queue
Queue for incremental processing with retry support.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `NCBI_API_KEY` | NCBI API key (optional, increases rate limit) | None |

## Rate Limiting

Default: 3 queries per second (conservative for NCBI)

With NCBI API key: Up to 10 queries per second

## Error Handling

- Automatic retry with exponential backoff (3 retries, 2x backoff)
- Checkpoint after every batch for resume capability
- Failed PMIDs tracked in `pmid_queue` for retry

## Output Format

### JSONL Export Fields

```json
{
  "id": "pubmed:12345678",
  "title": "Publication Title",
  "abstract": "Abstract text...",
  "year": 2024,
  "journal": "Journal Name",
  "doi": "10.1234/example",
  "mesh_terms": ["Term1", "Term2"],
  "publication_types": ["Clinical Trial"],
  "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
  "source_type": "rct",
  "quality_rank": 90
}
```

### Source Type Classification

| Type | Description | Quality Rank |
|------|-------------|--------------|
| guideline | Practice guidelines, consensus | 100 |
| meta_analysis | Meta-analyses, pooled analyses | 95 |
| rct | Randomized controlled trials | 90 |
| review | Systematic/narrative reviews | 80 |
| case_series | Case reports/series | 70 |
| other | Unclassified | 50 |

## License

This pipeline is for use with AesthetiCite. Respect NCBI usage guidelines and publisher copyrights.

"""
AesthetiCite — M5 Corpus Ingestion Engine
app/scripts/m5_ingest.py

Goal: Close the gap from 772,770 to 1,000,000 documents.

Strategy:
  Phase A — Journal-targeted ingestion (highest yield, lowest duplication)
             Pull by ISSN from 15 high-value journals M2/M4 missed
  Phase B — Specialty gap topics (wound healing, pharmacology, patient safety)
             Topics structurally absent from M2/M4 keyword queries
  Phase C — Multilingual expansion (French, Spanish, Portuguese, German, Italian, Arabic)
             Non-English literature largely untouched by M2/M4

Run:
    python app/scripts/m5_ingest.py --phase A
    python app/scripts/m5_ingest.py --phase B
    python app/scripts/m5_ingest.py --phase C
    python app/scripts/m5_ingest.py --all          # runs A then B then C
    python app/scripts/m5_ingest.py --status       # current document count

    python app/scripts/m5_ingest.py --phase A --dry-run   # count only, no insert

Env:
    DATABASE_URL=postgresql://...
    NCBI_API_KEY=...          # optional but strongly recommended — 10 req/s vs 3/s

Requirements:
    pip install psycopg2-binary requests fastembed tqdm
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, Iterator, List, Optional, Tuple

import psycopg2
import psycopg2.extras
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("m5")

DATABASE_URL: str = os.environ["DATABASE_URL"]
NCBI_API_KEY: str = os.environ.get("NCBI_API_KEY", "")
NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Respect NCBI rate limits
# With API key: 10 req/s — safe floor is 0.12 s between requests
# Without API key: 3 req/s — safe floor is 0.4 s
REQUEST_DELAY = 0.12 if NCBI_API_KEY else 0.4

CHUNK_SIZE = 800        # characters per chunk — consistent with existing ingest scripts
BATCH_EMBED = 32        # documents per embedding batch
MAX_RETRIES = 4
RETRY_BACKOFF = [2, 5, 15, 30]  # seconds


# ─────────────────────────────────────────────────────────────────────────────
# Phase A — Journal-targeted ingestion
#
# These journals were either missed by M2/M4 keyword queries or are
# high-value sources that deserve direct ISSN-based exhaustive pull.
# Sorted by relevance to aesthetic medicine.
# ─────────────────────────────────────────────────────────────────────────────

PHASE_A_JOURNALS = [
    # Core aesthetic medicine journals
    ("Aesthetic Surgery Journal",              "1090-820X", 2010, 2026),
    ("Aesthetics Journal",                     "2050-3717", 2014, 2026),
    ("Journal of Aesthetic Nursing",           "2048-9218", 2012, 2026),

    # Dermatology — high injectable content
    ("JAMA Dermatology",                       "2168-6068", 2013, 2026),
    ("British Journal of Dermatology",         "0007-0963", 2015, 2026),
    ("Journal of the European Academy of "
     "Dermatology and Venereology",            "0926-9959", 2015, 2026),
    ("Dermatologic Therapy",                   "1529-8019", 2015, 2026),
    ("Skin Research and Technology",           "0909-752X", 2015, 2026),

    # Plastic surgery with strong aesthetic content
    ("Annals of Plastic Surgery",              "0148-7043", 2015, 2026),
    ("Plastic and Reconstructive Surgery "
     "Global Open",                            "2169-7574", 2013, 2026),
    ("Journal of Craniofacial Surgery",        "1049-2275", 2015, 2026),

    # Laser and energy devices
    ("Lasers in Medical Science",              "0268-8921", 2015, 2026),
    ("Journal of Cosmetic and Laser Therapy",  "1476-4172", 2010, 2026),

    # Clinical safety and patient safety
    ("Journal of Patient Safety",              "1549-8417", 2015, 2026),
    ("BMJ Open",                               "2044-6055", 2018, 2026),
]


# ─────────────────────────────────────────────────────────────────────────────
# Phase B — Specialty gap topics
#
# These topics are structurally absent from M2/M4 because they weren't
# in the aesthetic medicine keyword list but directly support AesthetiCite's
# clinical content — pharmacology, wound healing, patient safety.
# ─────────────────────────────────────────────────────────────────────────────

PHASE_B_QUERIES = [
    # Hyaluronidase pharmacology
    ("hyaluronidase mechanism action clinical use",              "2010:2026"),
    ("hyaluronidase dose response skin injection",               "2012:2026"),
    ("hyaluronic acid degradation enzyme reversal",              "2010:2026"),

    # Botulinum toxin pharmacology depth
    ("botulinum toxin pharmacokinetics diffusion tissue",        "2010:2026"),
    ("botulinum toxin immunogenicity neutralizing antibodies",   "2012:2026"),
    ("onabotulinum abobotulinum incobotulinum comparison",       "2010:2026"),

    # Wound healing and tissue repair
    ("wound healing aesthetic procedure skin repair",            "2012:2026"),
    ("tissue necrosis prevention skin filler injection",         "2010:2026"),
    ("vascular anatomy face injection danger zones",             "2010:2026"),
    ("angular artery facial artery anatomy filler",              "2008:2026"),
    ("supratrochlear supraorbital artery anatomy",               "2010:2026"),
    ("labial artery lip anatomy injection risk",                 "2010:2026"),

    # Inflammation and biofilm
    ("biofilm aesthetic filler injectable implant",              "2012:2026"),
    ("inflammatory nodule filler late onset complication",       "2010:2026"),
    ("foreign body reaction filler granuloma treatment",         "2008:2026"),

    # Patient safety and clinical governance
    ("patient safety aesthetic medicine outpatient clinic",      "2015:2026"),
    ("clinical governance aesthetic practice UK",                "2015:2026"),
    ("informed consent aesthetic procedure complication",        "2015:2026"),
    ("medico-legal aesthetic medicine complaint outcome",        "2015:2026"),

    # Local anaesthetics in aesthetic procedures
    ("lidocaine topical aesthetic procedure skin",               "2010:2026"),
    ("local anaesthetic toxicity aesthetic injection",           "2010:2026"),

    # Skincare actives with clinical evidence
    ("retinol tretinoin skin ageing clinical trial",             "2015:2026"),
    ("vitamin C ascorbic acid skin photoprotection RCT",         "2015:2026"),
    ("niacinamide skin hyperpigmentation clinical study",        "2015:2026"),
    ("AHA BHA exfoliant clinical evidence skin quality",         "2015:2026"),
    ("sunscreen SPF photoprotection RCT skin cancer",            "2015:2026"),

    # Body contouring non-surgical
    ("cryolipolysis fat reduction clinical trial",               "2012:2026"),
    ("HIFU body contouring clinical evidence",                   "2013:2026"),
    ("radiofrequency skin tightening body clinical trial",       "2012:2026"),
    ("deoxycholic acid injection fat reduction kybella",         "2012:2026"),

    # Hair loss and PRP
    ("platelet rich plasma hair loss androgenetic alopecia RCT", "2015:2026"),
    ("PRP skin rejuvenation systematic review",                  "2015:2026"),
    ("minoxidil finasteride hair loss aesthetic",                "2015:2026"),

    # Regulation and device safety
    ("CE mark medical device aesthetic skin treatment",          "2017:2026"),
    ("FDA cleared aesthetic device skin safety",                 "2015:2026"),
    ("cosmetic filler regulation safety Europe UK",              "2015:2026"),

    # Thread lift and minimally invasive surgery
    ("thread lift PDO PLLA clinical outcome complication",       "2015:2026"),
    ("thread lift ptosis complication management",               "2015:2026"),

    # Scarring and pigmentation
    ("keloid hypertrophic scar treatment clinical trial",        "2010:2026"),
    ("post-inflammatory hyperpigmentation treatment evidence",   "2012:2026"),
    ("melasma treatment systematic review evidence",             "2010:2026"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Phase C — Multilingual expansion
#
# Each entry: (query_in_target_language, language_code, years)
# Language codes match PubMed's lang filter.
# ─────────────────────────────────────────────────────────────────────────────

PHASE_C_QUERIES = [
    # French
    ("médecine esthétique complication filler",          "fre", "2015:2026"),
    ("acide hyaluronique complication vasculaire",       "fre", "2015:2026"),
    ("toxine botulique ptose traitement",                "fre", "2015:2026"),
    ("laser dermatologie esthétique résultats",          "fre", "2015:2026"),
    ("médecine esthétique sécurité protocole",           "fre", "2015:2026"),
    ("augmentation lèvres résultats complication",       "fre", "2018:2026"),

    # Spanish
    ("medicina estética complicaciones relleno",         "spa", "2015:2026"),
    ("ácido hialurónico oclusión vascular tratamiento",  "spa", "2015:2026"),
    ("toxina botulínica dosificación seguridad",         "spa", "2015:2026"),
    ("laser rejuvenecimiento resultados clínicos",       "spa", "2015:2026"),
    ("seguridad procedimientos estéticos protocolo",     "spa", "2015:2026"),

    # Portuguese / Brazilian
    ("medicina estética complicações preenchedor",       "por", "2015:2026"),
    ("ácido hialurônico oclusão vascular tratamento",    "por", "2015:2026"),
    ("toxina botulínica dose segurança resultado",       "por", "2015:2026"),
    ("bioestimuladores colágeno PLLA HA resultados",     "por", "2015:2026"),
    ("laser rejuvenescimento evidência clínica",         "por", "2015:2026"),

    # German
    ("ästhetische Medizin Komplikation Filler",          "ger", "2015:2026"),
    ("Hyaluronsäure vaskuläre Komplikation Behandlung",  "ger", "2015:2026"),
    ("Botulinumtoxin Dosierung Sicherheit Ergebnis",     "ger", "2015:2026"),
    ("Laser Dermatologie ästhetisch klinische Studie",   "ger", "2015:2026"),

    # Italian
    ("medicina estetica complicanze filler acido",       "ita", "2015:2026"),
    ("tossina botulinica dosaggio sicurezza risultati",  "ita", "2015:2026"),
    ("laser ringiovanimento cutaneo studio clinico",     "ita", "2015:2026"),

    # Arabic (transliterated for PubMed)
    ("aesthetic medicine filler complication arabic",    "ara", "2018:2026"),
    ("botulinum toxin facial aesthetic arab",            "ara", "2018:2026"),
]


# ─────────────────────────────────────────────────────────────────────────────
# PubMed E-utilities — search + fetch
# ─────────────────────────────────────────────────────────────────────────────

def _ncbi_get(endpoint: str, params: Dict[str, str]) -> Optional[Dict]:
    """GET from NCBI with retry and rate limiting."""
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    params["retmode"] = "json"
    url = f"{NCBI_BASE}/{endpoint}"
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(REQUEST_DELAY)
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                logger.warning(f"NCBI request failed (attempt {attempt+1}): {e} — retrying in {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"NCBI request failed after {MAX_RETRIES} attempts: {e}")
                return None


def search_pmids_by_journal(
    issn: str, year_from: int, year_to: int, retmax: int = 10000
) -> List[str]:
    """Search PubMed for all PMIDs from a journal by ISSN within a year range."""
    data = _ncbi_get("esearch.fcgi", {
        "db": "pubmed",
        "term": f'"{issn}"[Journal] AND {year_from}:{year_to}[pdat]',
        "retmax": str(retmax),
        "sort": "pub date",
    })
    if not data:
        return []
    return data.get("esearchresult", {}).get("idlist", [])


def search_pmids_by_query(
    query: str, years: str = "2015:2026", lang: Optional[str] = None,
    retmax: int = 3000
) -> List[str]:
    """Search PubMed by free-text query with optional year range and language."""
    term = f"({query}) AND {years}[pdat]"
    if lang:
        term += f' AND "{lang}"[la]'
    data = _ncbi_get("esearch.fcgi", {
        "db": "pubmed",
        "term": term,
        "retmax": str(retmax),
        "sort": "pub date",
    })
    if not data:
        return []
    return data.get("esearchresult", {}).get("idlist", [])


def fetch_summaries(pmids: List[str]) -> Dict[str, Any]:
    """Fetch document summaries for a batch of PMIDs (max 200 per call)."""
    if not pmids:
        return {}
    data = _ncbi_get("esummary.fcgi", {
        "db": "pubmed",
        "id": ",".join(pmids),
    })
    if not data:
        return {}
    return data.get("result", {})


def fetch_abstract(pmid: str) -> str:
    """Fetch full abstract text for a single PMID via efetch."""
    time.sleep(REQUEST_DELAY)
    params: Dict[str, str] = {
        "db": "pubmed",
        "id": pmid,
        "rettype": "abstract",
        "retmode": "text",
    }
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    try:
        r = requests.get(f"{NCBI_BASE}/efetch.fcgi", params=params, timeout=20)
        r.raise_for_status()
        text = r.text.strip()
        # Strip the citation header lines (first 2 lines from efetch text output)
        lines = text.split("\n")
        clean = "\n".join(lines[2:]).strip() if len(lines) > 2 else text
        return clean[:4000]  # cap at 4000 chars
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Document processing
# ─────────────────────────────────────────────────────────────────────────────

def _clean(s: Optional[str]) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    return s[:2000]


def parse_summary(pmid: str, summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert PubMed esummary entry to AesthetiCite document dict."""
    if "error" in summary or not summary.get("uid"):
        return None

    title = _clean(summary.get("title", ""))
    if not title:
        return None

    # Journal and source
    source = _clean(summary.get("source", ""))
    journal = source or _clean(summary.get("fulljournalname", ""))

    # Year
    pub_date = summary.get("pubdate", "") or summary.get("epubdate", "")
    year: Optional[int] = None
    m = re.search(r"\b(19|20)\d{2}\b", pub_date)
    if m:
        year = int(m.group(0))

    # Authors
    authors_list = summary.get("authors", [])
    authors_str = ""
    if authors_list:
        names = [a.get("name", "") for a in authors_list[:5] if a.get("name")]
        authors_str = ", ".join(names)
        if len(authors_list) > 5:
            authors_str += " et al."

    # DOI and URL
    articleids = summary.get("articleids", [])
    doi = ""
    for aid in articleids:
        if aid.get("idtype") == "doi":
            doi = aid.get("value", "")
            break
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    if doi:
        url = f"https://doi.org/{doi}"

    # Publication type → document_type
    # Guard: PubMed esummary occasionally returns bare strings in the pubtype list
    pub_types = [
        p.get("value", "").lower()
        for p in summary.get("pubtype", [])
        if isinstance(p, dict)
    ]

    if any("guideline" in p or "practice guideline" in p or "consensus" in p for p in pub_types):
        document_type = "guideline"
    elif any("systematic" in p or "meta-analysis" in p for p in pub_types):
        document_type = "review"
    elif any("randomized controlled trial" in p or "clinical trial" in p for p in pub_types):
        document_type = "journal_article"
    elif any("review" in p for p in pub_types):
        document_type = "review"
    elif any("case report" in p or "case series" in p for p in pub_types):
        document_type = "case_report"
    else:
        document_type = "journal_article"

    # Language
    lang = summary.get("lang", ["eng"])
    language = lang[0] if isinstance(lang, list) and lang else "eng"

    # Abstract (from esummary — often truncated; full fetch happens separately)
    abstract = _clean(summary.get("abstracttext", ""))

    return {
        "pmid": pmid,
        "source_id": f"PMID_{pmid}",
        "title": title,
        "abstract": abstract,
        "journal": journal,
        "year": year,
        "authors": authors_str,
        "doi": doi,
        "url": url,
        "language": language,
        "document_type": document_type,
    }


def make_chunks(
    title: str,
    abstract: str,
    chunk_size: int = CHUNK_SIZE,
) -> List[str]:
    """Split title + abstract into overlapping chunks for embedding."""
    full_text = f"{title}. {abstract}".strip()
    if not full_text:
        return []
    chunks = []
    words = full_text.split()
    current: List[str] = []
    current_len = 0
    for word in words:
        current.append(word)
        current_len += len(word) + 1
        if current_len >= chunk_size:
            chunks.append(" ".join(current))
            # 20% overlap
            overlap = max(1, len(current) // 5)
            current = current[-overlap:]
            current_len = sum(len(w) + 1 for w in current)
    if current:
        chunks.append(" ".join(current))
    return chunks if chunks else [full_text[:chunk_size]]


# ─────────────────────────────────────────────────────────────────────────────
# Embedding — fastembed, same model as production (BAAI/bge-small-en-v1.5, 384-dim)
# ─────────────────────────────────────────────────────────────────────────────

_embed_model = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from fastembed import TextEmbedding
        logger.info("Loading fastembed BAAI/bge-small-en-v1.5 (384-dim)...")
        _embed_model = TextEmbedding("BAAI/bge-small-en-v1.5")
        logger.info("Embedding model ready.")
    return _embed_model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a batch of texts. Returns list of 384-dim float vectors."""
    model = _get_embed_model()
    return [v.tolist() for v in model.embed(texts)]


# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(DATABASE_URL)


def get_doc_count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM documents;")
        return cur.fetchone()[0]


def source_id_exists(conn, source_id: str) -> bool:
    """Check whether a document with this source_id already exists."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM documents WHERE source_id = %s LIMIT 1;",
            (source_id,)
        )
        return cur.fetchone() is not None


def insert_document(
    conn, doc: Dict[str, Any], specialty: str = "", domain: str = "aesthetic_medicine"
) -> Optional[str]:
    """
    Insert a document row. Returns the new doc UUID string, or None if it
    already existed (ON CONFLICT on source_id).
    """
    doc_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO documents (
                id, source_id, title, abstract, authors,
                organization_or_journal, year, document_type,
                domain, specialty, language, url, status,
                created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, 'active',
                NOW(), NOW()
            )
            ON CONFLICT (source_id) DO NOTHING
            RETURNING id;
        """, (
            doc_id,
            doc["source_id"],
            doc["title"],
            doc.get("abstract", ""),
            doc.get("authors", ""),
            doc.get("journal", ""),
            doc.get("year"),
            doc["document_type"],
            domain,
            specialty,
            doc.get("language", "eng"),
            doc.get("url", ""),
        ))
        row = cur.fetchone()
        if not row:
            return None  # conflict — already existed
        return row[0]


def _flush_chunk_batch(conn, batch: List[Tuple[str, str]]) -> int:
    """
    Embed and insert a batch of (doc_id, chunk_text) pairs.
    Returns the number of chunk rows written.
    """
    if not batch:
        return 0
    doc_ids, texts = zip(*batch)
    try:
        embeddings = embed_texts(list(texts))
    except Exception as e:
        logger.error(f"Embedding batch failed: {e}")
        return 0
    inserted = 0
    with conn.cursor() as cur:
        for doc_id, text, emb in zip(doc_ids, texts, embeddings):
            chunk_id = str(uuid.uuid4())
            # Determine next chunk_index for this document
            cur.execute(
                "SELECT COALESCE(MAX(chunk_index), -1) + 1 FROM chunks WHERE document_id = %s",
                (doc_id,)
            )
            chunk_index = cur.fetchone()[0]
            emb_str = "[" + ",".join(f"{v:.6f}" for v in emb) + "]"
            cur.execute("""
                INSERT INTO chunks (id, document_id, chunk_index, text, embedding, created_at)
                VALUES (%s, %s, %s, %s, %s::vector, NOW())
                ON CONFLICT DO NOTHING;
            """, (chunk_id, doc_id, chunk_index, text, emb_str))
            inserted += 1
    return inserted


# ─────────────────────────────────────────────────────────────────────────────
# Core ingestion loop
# ─────────────────────────────────────────────────────────────────────────────

def ingest_pmids(
    pmids: List[str],
    specialty: str = "",
    domain: str = "aesthetic_medicine",
    dry_run: bool = False,
    fetch_full_abstracts: bool = True,
) -> Tuple[int, int]:
    """
    Fetch metadata for a list of PMIDs from PubMed and insert new ones.
    Returns (docs_inserted, chunks_inserted).
    Fully idempotent — every insert uses ON CONFLICT DO NOTHING on source_id.
    """
    if not pmids:
        return 0, 0

    conn = get_conn()
    docs_inserted = 0
    chunks_inserted = 0

    # Filter out PMIDs already in DB before making any API calls
    new_pmids = [p for p in pmids if not source_id_exists(conn, f"PMID_{p}")]
    if not new_pmids:
        logger.info(f"  All {len(pmids)} PMIDs already in database — skipping")
        conn.close()
        return 0, 0

    logger.info(f"  {len(new_pmids)} new PMIDs to process (of {len(pmids)} found)")

    if dry_run:
        logger.info(f"  [DRY RUN] Would insert up to {len(new_pmids)} documents")
        conn.close()
        return len(new_pmids), 0

    # Process in summary batches of 200 (NCBI limit per request)
    batch_size = 200
    chunk_embed_batch: List[Tuple[str, str]] = []  # (doc_id, chunk_text)

    for batch_start in range(0, len(new_pmids), batch_size):
        batch = new_pmids[batch_start: batch_start + batch_size]
        logger.info(f"  Fetching summaries {batch_start + 1}–{batch_start + len(batch)}…")

        summaries = fetch_summaries(batch)

        for pmid in batch:
            if pmid not in summaries:
                continue
            doc = parse_summary(pmid, summaries[pmid])
            if not doc:
                continue

            # Fetch full abstract if esummary returned nothing (common) or truncated it
            if fetch_full_abstracts and len(doc.get("abstract", "")) < 200:
                full_abs = fetch_abstract(pmid)
                if full_abs:
                    doc["abstract"] = full_abs

            doc_id = insert_document(conn, doc, specialty=specialty, domain=domain)
            if not doc_id:
                continue  # already existed — conflict

            docs_inserted += 1

            # Build chunks for embedding
            chunks = make_chunks(doc["title"], doc.get("abstract", ""))
            for chunk_text in chunks:
                chunk_embed_batch.append((doc_id, chunk_text))

            # Embed and flush when the buffer is large enough
            if len(chunk_embed_batch) >= BATCH_EMBED * 3:
                chunks_inserted += _flush_chunk_batch(conn, chunk_embed_batch)
                chunk_embed_batch = []

        conn.commit()

    # Flush any remaining chunks
    if chunk_embed_batch:
        chunks_inserted += _flush_chunk_batch(conn, chunk_embed_batch)
        conn.commit()

    conn.close()
    return docs_inserted, chunks_inserted


# ─────────────────────────────────────────────────────────────────────────────
# Phase runners
# ─────────────────────────────────────────────────────────────────────────────

def run_phase_a(dry_run: bool = False) -> None:
    """Journal-targeted ingestion by ISSN."""
    logger.info("═══ PHASE A — Journal-targeted ingestion ═══")
    conn = get_conn()
    start_count = get_doc_count(conn)
    conn.close()
    logger.info(f"Documents at start: {start_count:,}")

    total_docs = 0
    total_chunks = 0

    for journal_name, issn, year_from, year_to in PHASE_A_JOURNALS:
        logger.info(f"\nJournal: {journal_name} (ISSN {issn}) {year_from}–{year_to}")
        pmids = search_pmids_by_journal(issn, year_from, year_to)
        logger.info(f"  Found {len(pmids)} PMIDs")
        if not pmids:
            continue

        specialty = "aesthetic_medicine" if any(
            kw in journal_name.lower()
            for kw in ["aesthetic", "cosmetic", "dermatologic", "plastic", "laser"]
        ) else "dermatology"

        docs, chunks = ingest_pmids(pmids, specialty=specialty, dry_run=dry_run)
        total_docs += docs
        total_chunks += chunks
        logger.info(f"  Inserted: {docs} docs, {chunks} chunks")

    conn = get_conn()
    end_count = get_doc_count(conn)
    conn.close()
    logger.info(
        f"\nPhase A complete. Documents: {start_count:,} → {end_count:,} "
        f"(+{end_count - start_count:,})"
    )
    logger.info(f"Total inserted: {total_docs} docs, {total_chunks} chunks")


def run_phase_b(dry_run: bool = False) -> None:
    """Specialty gap topic ingestion."""
    logger.info("═══ PHASE B — Specialty gap topics ═══")
    conn = get_conn()
    start_count = get_doc_count(conn)
    conn.close()
    logger.info(f"Documents at start: {start_count:,}")

    total_docs = 0
    total_chunks = 0

    for query, years in PHASE_B_QUERIES:
        logger.info(f"\nQuery: {query[:60]}… ({years})")
        pmids = search_pmids_by_query(query, years=years)
        logger.info(f"  Found {len(pmids)} PMIDs")
        if not pmids:
            continue

        specialty = "aesthetic_medicine"
        if any(k in query.lower() for k in ["wound", "tissue", "necrosis", "artery", "anatomy"]):
            specialty = "skin_procedures"
        elif any(k in query.lower() for k in ["patient safety", "governance", "medico-legal", "consent"]):
            specialty = "clinical_governance"
        elif any(k in query.lower() for k in ["pharmacology", "lidocaine", "anaesthetic"]):
            specialty = "pharmacology"

        docs, chunks = ingest_pmids(pmids, specialty=specialty, dry_run=dry_run)
        total_docs += docs
        total_chunks += chunks
        logger.info(f"  Inserted: {docs} docs, {chunks} chunks")

    conn = get_conn()
    end_count = get_doc_count(conn)
    conn.close()
    logger.info(
        f"\nPhase B complete. Documents: {start_count:,} → {end_count:,} "
        f"(+{end_count - start_count:,})"
    )
    logger.info(f"Total inserted: {total_docs} docs, {total_chunks} chunks")


def run_phase_c(dry_run: bool = False) -> None:
    """Multilingual expansion."""
    logger.info("═══ PHASE C — Multilingual expansion ═══")
    conn = get_conn()
    start_count = get_doc_count(conn)
    conn.close()
    logger.info(f"Documents at start: {start_count:,}")

    total_docs = 0
    total_chunks = 0

    lang_labels = {
        "fre": "French", "spa": "Spanish", "por": "Portuguese",
        "ger": "German", "ita": "Italian", "ara": "Arabic",
    }

    for query, lang, years in PHASE_C_QUERIES:
        logger.info(f"\n[{lang_labels.get(lang, lang)}] {query[:60]}…")
        pmids = search_pmids_by_query(query, years=years, lang=lang)
        logger.info(f"  Found {len(pmids)} PMIDs")
        if not pmids:
            continue

        docs, chunks = ingest_pmids(pmids, specialty="aesthetic_medicine", dry_run=dry_run)
        total_docs += docs
        total_chunks += chunks
        logger.info(f"  Inserted: {docs} docs, {chunks} chunks")

    conn = get_conn()
    end_count = get_doc_count(conn)
    conn.close()
    logger.info(
        f"\nPhase C complete. Documents: {start_count:,} → {end_count:,} "
        f"(+{end_count - start_count:,})"
    )
    logger.info(f"Total inserted: {total_docs} docs, {total_chunks} chunks")


def print_status() -> None:
    """Print current corpus status."""
    conn = get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT COUNT(*) AS n FROM documents;")
        doc_count = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM chunks;")
        chunk_count = cur.fetchone()["n"]
        cur.execute("""
            SELECT document_type, COUNT(*) AS n
            FROM documents
            GROUP BY document_type
            ORDER BY n DESC
            LIMIT 10;
        """)
        types = cur.fetchall()
        cur.execute("""
            SELECT language, COUNT(*) AS n
            FROM documents
            GROUP BY language
            ORDER BY n DESC
            LIMIT 10;
        """)
        langs = cur.fetchall()
        cur.execute("""
            SELECT MIN(year) AS min_year, MAX(year) AS max_year,
                   COUNT(*) FILTER (WHERE year >= 2020) AS recent
            FROM documents WHERE year IS NOT NULL;
        """)
        years = cur.fetchone()
    conn.close()

    logger.info("─── M5 Corpus Status ───────────────────────────────")
    logger.info(f"Documents : {doc_count:,}")
    logger.info(f"Chunks    : {chunk_count:,}")
    logger.info(f"Gap to 1M : {max(0, 1_000_000 - doc_count):,}")
    if years and years["min_year"]:
        logger.info(f"Year range: {years['min_year']} – {years['max_year']}")
        logger.info(
            f"Post-2020 : {years['recent']:,} "
            f"({years['recent'] * 100 // doc_count if doc_count else 0}%)"
        )
    logger.info("Document types:")
    for r in types:
        logger.info(f"  {r['document_type'] or 'NULL':<30} {r['n']:>8,}")
    logger.info("Languages:")
    for r in langs:
        logger.info(f"  {r['language'] or 'NULL':<10} {r['n']:>8,}")
    logger.info("────────────────────────────────────────────────────")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="AesthetiCite M5 ingestion engine")
    parser.add_argument("--phase", choices=["A", "B", "C"], help="Run a specific phase")
    parser.add_argument("--all",   action="store_true", help="Run all phases A → B → C")
    parser.add_argument("--status", action="store_true", help="Print corpus status and exit")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count documents only — no database writes"
    )
    args = parser.parse_args()

    if args.status:
        print_status()
        return

    if not args.phase and not args.all:
        parser.print_help()
        return

    if args.dry_run:
        logger.info("DRY RUN MODE — no documents will be inserted")

    if args.all:
        run_phase_a(dry_run=args.dry_run)
        run_phase_b(dry_run=args.dry_run)
        run_phase_c(dry_run=args.dry_run)
        print_status()
    elif args.phase == "A":
        run_phase_a(dry_run=args.dry_run)
        print_status()
    elif args.phase == "B":
        run_phase_b(dry_run=args.dry_run)
        print_status()
    elif args.phase == "C":
        run_phase_c(dry_run=args.dry_run)
        print_status()


if __name__ == "__main__":
    main()

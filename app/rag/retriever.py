from __future__ import annotations
import logging
import re
import time
from typing import List, Dict, Optional, Tuple, Set
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.config import settings
from app.rag.embedder import embed_text
from app.rag.cache import embed_text_cached
from app.rag.hnsw_store import hnsw_store

logger = logging.getLogger(__name__)

UNIT_PATTERNS = [
    r'mg', r'g', r'kg', r'mcg', r'μg', r'ug',
    r'mL', r'ml', r'L', r'cc',
    r'Units?', r'IU', r'U',
    r'mmol', r'mol', r'mEq',
    r'%', r'percent',
    r'mg/mL', r'mg/kg', r'mcg/kg', r'U/kg', r'mg/dL', r'mmol/L',
    r'mg/m2', r'mg/m²',
    r'hours?', r'hrs?', r'minutes?', r'mins?', r'days?', r'weeks?', r'months?',
    r'mm', r'cm', r'inches?', r'in',
    r'bpm', r'mmHg', r'kPa',
]

NUMERIC_WITH_UNIT_RE = re.compile(
    r'(\d+(?:\.\d+)?(?:\s*[-–to]+\s*\d+(?:\.\d+)?)?)\s*(' + '|'.join(UNIT_PATTERNS) + r')',
    re.IGNORECASE
)

DOSAGE_KEYWORDS = {
    'dose', 'dosage', 'dosing', 'maximum dose', 'max dose', 'minimum dose', 'min dose',
    'concentration', 'quantity', 'limit', 'recommended dose',
    'units', 'milligrams', 'mg/kg', 'mcg/kg', 'mg/m2',
    'toxic dose', 'lethal dose', 'therapeutic dose', 'loading dose', 'maintenance dose',
    'infusion rate', 'bolus dose', 'titrate', 'titration',
    'renal dosing', 'hepatic dosing', 'dose adjustment', 'creatinine clearance',
    'pediatric dose', 'adult dose', 'geriatric dose', 'weight-based dosing', 'bsa dosing',
}

SQL_UNIFIED_ALL = """
WITH
v AS (
  SELECT c.id,
         (c.embedding <=> CAST(:qvec AS vector(384))) AS vdist
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE d.status = 'active'
    AND c.embedding IS NOT NULL
  ORDER BY c.embedding <=> CAST(:qvec AS vector(384))
  LIMIT 80
),
f AS (
  SELECT c.id,
         ts_rank_cd(c.tsv, websearch_to_tsquery('english', :q)) AS fts
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE d.status = 'active'
    AND c.tsv @@ websearch_to_tsquery('english', :q)
  ORDER BY fts DESC
  LIMIT 80
),
u AS (
  SELECT id,
         min(vdist) AS vdist,
         max(fts)   AS fts
  FROM (
    SELECT id, vdist, NULL::float AS fts FROM v
    UNION ALL
    SELECT id, NULL::float, fts FROM f
  ) s
  GROUP BY id
),
ranked AS (
  SELECT *
  FROM u
  ORDER BY
    COALESCE(vdist, 1e9) ASC,
    COALESCE(fts, 0) DESC
  LIMIT :k
)
SELECT
  d.source_id,
  d.title,
  d.year,
  d.organization_or_journal,
  d.document_type,
  d.domain,
  c.page_or_section,
  COALESCE(c.evidence_level, d.document_type) AS evidence_level,
  c.text,
  r.vdist,
  r.fts AS krank,
  COALESCE(d.url, '') AS url
FROM ranked r
JOIN chunks c ON c.id = r.id
JOIN documents d ON d.id = c.document_id
ORDER BY
  COALESCE(r.vdist, 1e9) ASC,
  COALESCE(r.fts, 0) DESC;
"""

SQL_UNIFIED_DOMAIN = """
WITH
v AS (
  SELECT c.id,
         (c.embedding <=> CAST(:qvec AS vector(384))) AS vdist
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE d.status = 'active'
    AND c.embedding IS NOT NULL
    AND d.domain = :domain
  ORDER BY c.embedding <=> CAST(:qvec AS vector(384))
  LIMIT 80
),
f AS (
  SELECT c.id,
         ts_rank_cd(c.tsv, websearch_to_tsquery('english', :q)) AS fts
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE d.status = 'active'
    AND d.domain = :domain
    AND c.tsv @@ websearch_to_tsquery('english', :q)
  ORDER BY fts DESC
  LIMIT 80
),
u AS (
  SELECT id,
         min(vdist) AS vdist,
         max(fts)   AS fts
  FROM (
    SELECT id, vdist, NULL::float AS fts FROM v
    UNION ALL
    SELECT id, NULL::float, fts FROM f
  ) s
  GROUP BY id
),
ranked AS (
  SELECT *
  FROM u
  ORDER BY
    COALESCE(vdist, 1e9) ASC,
    COALESCE(fts, 0) DESC
  LIMIT :k
)
SELECT
  d.source_id,
  d.title,
  d.year,
  d.organization_or_journal,
  d.document_type,
  d.domain,
  c.page_or_section,
  COALESCE(c.evidence_level, d.document_type) AS evidence_level,
  c.text,
  r.vdist,
  r.fts AS krank,
  COALESCE(d.url, '') AS url
FROM ranked r
JOIN chunks c ON c.id = r.id
JOIN documents d ON d.id = c.document_id
ORDER BY
  COALESCE(r.vdist, 1e9) ASC,
  COALESCE(r.fts, 0) DESC;
"""

SQL_DRUG_TITLE_SEARCH = """
SELECT
  d.source_id,
  d.title,
  d.year,
  d.organization_or_journal,
  d.document_type,
  d.domain,
  c.page_or_section,
  COALESCE(c.evidence_level, d.document_type) AS evidence_level,
  c.text,
  1.0 AS drug_match
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE d.status = 'active'
  AND d.document_type = 'prescribing_information'
  AND d.title ILIKE :drug_pattern
ORDER BY d.year DESC NULLS LAST
LIMIT :k;
"""


def is_numerical_query(question: str) -> bool:
    """Detect if a query is asking about numerical/dosage information."""
    q_lower = question.lower()
    
    # Check for dosage keywords
    for keyword in DOSAGE_KEYWORDS:
        if keyword in q_lower:
            return True
    
    # Check for numerical patterns with units in the query
    if NUMERIC_WITH_UNIT_RE.search(question):
        return True
    
    # Check for common dosage question patterns
    dosage_patterns = [
        r'how\s+much',
        r'how\s+many',
        r'what\s+is\s+the\s+(max|min|dose|dosage|limit)',
        r'(max|maximum|recommended)\s+(dose|dosage|amount)',
        r'\d+\s*(mg|ml|units?|g|mcg)',
    ]
    for pattern in dosage_patterns:
        if re.search(pattern, q_lower):
            return True
    
    return False


def extract_numerical_patterns(question: str) -> List[str]:
    """Extract numerical values with units from the question."""
    matches = NUMERIC_WITH_UNIT_RE.findall(question)
    patterns = []
    for value, unit in matches:
        # Create regex pattern to match similar values
        # Handle ranges like "10-20 mg"
        clean_value = re.sub(r'\s*[-–to]+\s*', r'\\s*[-–to]+\\s*', value)
        patterns.append(f"{clean_value}\\s*{unit}")
    return patterns


def extract_drug_names(question: str) -> Set[str]:
    """Extract potential drug names from question for targeted numerical search."""
    # Common drug name patterns (capitalized words, brand names)
    words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', question)
    # Also get lowercase potential drug names
    words.extend(re.findall(r'\b[a-z]{4,}\b', question.lower()))
    # Filter out common non-drug words
    stop_words = {'what', 'where', 'when', 'which', 'about', 'maximum', 'minimum', 
                  'dose', 'dosage', 'should', 'could', 'would', 'have', 'been',
                  'this', 'that', 'with', 'from', 'into', 'they', 'there', 'their'}
    return set(w for w in words if w.lower() not in stop_words and len(w) > 3)


def build_numeric_search_pattern(question: str) -> Optional[str]:
    """Build a regex pattern to find chunks with relevant numerical content."""
    drug_names = extract_drug_names(question)
    
    # Extract any specific numbers mentioned in query
    numbers = re.findall(r'\d+(?:\.\d+)?', question)
    
    # Build pattern components
    components = []
    
    # Match drug names with nearby numbers
    for drug in list(drug_names)[:3]:  # Limit to top 3
        if len(drug) >= 4:
            components.append(f"({drug}.*\\d+|\\d+.*{drug})")
    
    # Match specific numbers with units
    for num in numbers[:2]:  # Limit to 2 numbers
        components.append(f"{num}\\s*(mg|mL|ml|Units?|g|mcg|%)")
    
    # If asking about max/min doses, look for those patterns
    q_lower = question.lower()
    if any(kw in q_lower for kw in ['max', 'maximum', 'limit']):
        components.append(r"(maximum|max|limit|not\s+exceed|up\s+to)\s*[:\s]*\d+")
    if any(kw in q_lower for kw in ['min', 'minimum']):
        components.append(r"(minimum|min|at\s+least)\s*[:\s]*\d+")
    if 'recommended' in q_lower or 'dose' in q_lower:
        components.append(r"(recommended|dose|dosage|dosing)[:\s]*\d+")
    
    if not components:
        return None
    
    return '|'.join(components)


def count_numerical_density(text: str) -> float:
    """Calculate the density of numerical values with units in text."""
    matches = NUMERIC_WITH_UNIT_RE.findall(text)
    if not matches:
        return 0.0
    
    # Count unique numerical values
    unique_values = set(f"{v}{u.lower()}" for v, u in matches)
    
    # Normalize by text length (per 1000 chars)
    text_len = max(len(text), 1)
    density = len(unique_values) / (text_len / 1000.0)
    
    # Cap at 1.0
    return min(1.0, density / 5.0)  # 5 unique values per 1000 chars = max score


def numerical_relevance_bonus(text: str, question: str, title: str = "") -> float:
    """Calculate bonus for chunks that contain numerical values matching query context."""
    bonus = 0.0
    q_lower = question.lower()
    t_lower = text.lower()
    title_lower = title.lower()
    
    # Extract drug names from query
    drug_names = extract_drug_names(question)
    
    # Strong bonus for title containing queried drug name (exact product match)
    for drug in drug_names:
        drug_lower = drug.lower()
        if len(drug_lower) >= 4 and drug_lower in title_lower:
            bonus += 0.35  # Strong boost for matching product PI
            break
    
    # If query asks about specific numbers, boost if chunk contains them
    query_numbers = set(re.findall(r'\d+(?:\.\d+)?', question))
    text_numbers = set(re.findall(r'\d+(?:\.\d+)?', text))
    
    # Exact number match bonus
    matching_numbers = query_numbers & text_numbers
    if matching_numbers:
        bonus += 0.15 * min(len(matching_numbers), 2)  # Up to 0.30 for matching numbers
    
    # Drug name with number proximity bonus
    for drug in drug_names:
        drug_lower = drug.lower()
        if drug_lower in t_lower:
            # Check if drug name is near a number in the text
            pattern = f"(?:{drug_lower}.{{0,50}}\\d|\\d.{{0,50}}{drug_lower})"
            if re.search(pattern, t_lower, re.IGNORECASE):
                bonus += 0.15
                break
    
    # Max/min dose pattern bonus
    if any(kw in q_lower for kw in ['max', 'maximum', 'limit']):
        if re.search(r'(maximum|max|limit|not\s+exceed|up\s+to)\s*[:\s]*\d+', t_lower):
            bonus += 0.25
    if any(kw in q_lower for kw in ['min', 'minimum']):
        if re.search(r'(minimum|min|at\s+least)\s*[:\s]*\d+', t_lower):
            bonus += 0.25
    
    # Prescribing info / dosing section bonus (dosage pattern in text)
    if re.search(r'(dosage|dosing|dose|maximum\s+dose|recommended)', t_lower):
        bonus += 0.10
    
    return min(bonus, 0.65)  # Cap total bonus

def _preferred_doc_types():
    return [x.strip().lower() for x in settings.PREFERRED_DOC_TYPES.split(",") if x.strip()]

def _doc_type_bonus(doc_type: str | None) -> float:
    dt = (doc_type or "").strip().lower()
    pref = _preferred_doc_types()
    if dt in pref:
        if dt in ("guideline", "consensus", "ifu"):
            return 0.22
        return 0.12
    return 0.0

def _recency_bonus(year: int | None) -> float:
    if not year:
        return 0.0
    if year >= settings.MIN_YEAR_PREFERRED:
        return 0.08
    return 0.0

def _truncate_text(t: str) -> str:
    return t if len(t) <= 8000 else t[:8000]

def retrieve_db(db: Session, question: str, domain: Optional[str] = None, k: int = 0) -> List[Dict]:
    """
    Unified single-query hybrid retrieval (vector + FTS) using
    STORED tsv/text_norm columns with GIN indexes. One SQL CTE replaces
    multiple parallel queries, eliminating ThreadPool overhead and connection churn.
    """
    if not k:
        k_final = settings.RERANK_TOP_N
    else:
        k_final = k

    numerical_query = is_numerical_query(question)
    if numerical_query:
        logger.info(f"Numerical query detected: {question[:80]}...")

    t0 = time.monotonic()
    qvec = embed_text_cached(question, embed_text)
    qvec_str = str(qvec)
    t_embed = time.monotonic() - t0

    t1 = time.monotonic()
    db.execute(text("SET LOCAL hnsw.ef_search = 80"))
    db.execute(text("SET LOCAL ivfflat.probes = 5"))  # lists=100, probes=5 → ~93% recall

    candidate_k = max(k_final * 3, 40)
    params = {
        "qvec": qvec_str,
        "q": question,
        "k": int(candidate_k),
    }
    if domain:
        params["domain"] = domain
        rows = db.execute(text(SQL_UNIFIED_DOMAIN), params).mappings().all()
    else:
        rows = db.execute(text(SQL_UNIFIED_ALL), params).mappings().all()

    t_sql = time.monotonic() - t1
    logger.info(f"Unified retrieval: {len(rows)} candidates in {t_sql:.2f}s (embed {t_embed:.2f}s)")

    drug_title_rows = []
    if numerical_query:
        try:
            drug_names = extract_drug_names(question)
            for drug in list(drug_names)[:3]:
                if len(drug) >= 4:
                    drug_pattern = f"%{drug}%"
                    dr = db.execute(
                        text(SQL_DRUG_TITLE_SEARCH),
                        {"drug_pattern": drug_pattern, "k": 10}
                    ).mappings().all()
                    drug_title_rows.extend(dr)
                    if dr:
                        logger.info(f"Drug-title search found {len(dr)} PI chunks")
        except Exception as e:
            logger.warning(f"Drug-title search failed: {e}")

    merged = {}
    def add_row(r, kind: str):
        key = (r["source_id"], r.get("page_or_section") or "")
        if key not in merged:
            merged[key] = {
                "source_id": r["source_id"],
                "title": r["title"],
                "year": r["year"],
                "organization_or_journal": r["organization_or_journal"],
                "page_or_section": r.get("page_or_section"),
                "evidence_level": r.get("evidence_level"),
                "document_type": r.get("document_type"),
                "domain": r.get("domain"),
                "text": _truncate_text(r.get("text") or ""),
                "vdist": None,
                "krank": None,
                "num_match": False,
                "url": r.get("url", "") or "",
            }
        if r.get("vdist") is not None:
            merged[key]["vdist"] = float(r["vdist"])
        if r.get("krank") is not None and r["krank"]:
            merged[key]["krank"] = float(r["krank"])
        if kind == "drug":
            merged[key]["drug_match"] = True

    for r in rows:
        add_row(r, "unified")
    for r in drug_title_rows:
        add_row(r, "drug")

    candidates = list(merged.values())
    max_krank = max((c["krank"] or 0.0 for c in candidates), default=1.0) or 1.0

    for c in candidates:
        v_sim = 0.0
        if c["vdist"] is not None:
            v_sim = max(0.0, 1.0 - (c["vdist"] / 2.0))

        k_sim = 0.0
        if c["krank"] is not None and c["krank"] > 0:
            k_sim = min(1.0, c["krank"] / max_krank)

        bonus = _doc_type_bonus(c.get("document_type")) + _recency_bonus(c.get("year"))

        num_bonus = 0.0
        if numerical_query:
            chunk_text = c.get("text", "")
            chunk_title = c.get("title", "")
            if c.get("drug_match"):
                num_bonus += 0.40
            num_bonus += numerical_relevance_bonus(chunk_text, question, chunk_title)
            doc_type = (c.get("document_type") or "").lower()
            if doc_type == "prescribing_information":
                num_bonus += 0.20

        c["_score"] = (0.55 * v_sim) + (0.45 * k_sim) + bonus + num_bonus
        c["_num_bonus"] = num_bonus

    pref = _preferred_doc_types()
    preferred = [c for c in candidates if (c.get("document_type") or "").lower() in pref]
    if len(preferred) >= 8:
        candidates = preferred

    candidates.sort(key=lambda x: x.get("_score", 0.0), reverse=True)
    return candidates[:k_final]


def retrieve_hnsw(question: str, k: int = 12) -> List[Dict]:
    """
    Fast HNSW-only retrieval for sub-second latency.
    Returns chunk metadata with text, title, source_type, url/doi.
    Falls back to empty list if HNSW not available.
    """
    if not hnsw_store.ok:
        logger.warning("HNSW store not available for fast retrieval")
        return []
    
    try:
        from app.openai_wiring import embed
        qvec = embed(question)
    except Exception as e:
        logger.warning(f"Failed to embed for HNSW search: {e}")
        qvec = embed_text_cached(question, embed_text)
    
    results = hnsw_store.search(qvec, k=k)
    logger.info(f"HNSW retrieved {len(results)} chunks for: {question[:60]}...")
    return results


def retrieve_hybrid(db: Session, question: str, domain: Optional[str] = None, k: int = 12) -> List[Dict]:
    """
    Hybrid retrieval: HNSW first (fast), then DB if needed.
    Best of both worlds: sub-second for cached index, full coverage via DB.
    """
    hnsw_results = retrieve_hnsw(question, k=k)
    
    if len(hnsw_results) >= k:
        return hnsw_results[:k]
    
    db_results = retrieve_db(db=db, question=question, domain=domain, k=k)
    
    seen = set()
    merged = []
    for r in hnsw_results:
        key = (r.get("title", ""), r.get("text", "")[:100])
        if key not in seen:
            seen.add(key)
            merged.append(r)
    
    for r in db_results:
        key = (r.get("title", ""), r.get("text", "")[:100])
        if key not in seen:
            seen.add(key)
            merged.append(r)
    
    merged.sort(key=lambda x: x.get("_score", 0.0), reverse=True)
    return merged[:k]

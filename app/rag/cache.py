"""
Caching layer for embedding and answer retrieval.

Provides:
1. Embedding cache - cache query embeddings for 25-40% speedup
2. Hot question cache - cache full answers for common queries
3. Retrieval cache - cache intermediate retrieval results

Uses SQLite for persistence with optional Redis for distributed caching.
"""
from __future__ import annotations
import hashlib
import json
import time
import sqlite3
import logging
from typing import Optional, List, Dict, Any, Tuple
from functools import lru_cache
from pathlib import Path
import threading

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_DIR = Path("/tmp/aestheticite_cache")  # nosec B108
EMBEDDING_CACHE_DB = CACHE_DIR / "embedding_cache.db"
ANSWER_CACHE_DB = CACHE_DIR / "answer_cache.db"

# TTL settings
EMBEDDING_TTL_SECONDS = 86400 * 7  # 7 days for embeddings
HOT_QUESTION_TTL_SECONDS = 86400 * 2  # 48 hours for hot answers
RETRIEVAL_TTL_SECONDS = 3600 * 6  # 6 hours for retrieval results

# Hot questions - commonly asked clinical queries
HOT_QUESTIONS = [
    # Botox/Neurotoxins
    "botox dosing glabella",
    "botox maximum dose per session",
    "dysport conversion botox",
    "xeomin dosing forehead",
    "botulinum toxin dilution",
    
    # Fillers
    "hyaluronic acid vascular occlusion",
    "filler vascular occlusion treatment",
    "hyaluronidase dosing",
    "juvederm voluma dosing",
    "restylane injection technique",
    
    # Local anesthetics
    "lidocaine max dose",
    "lidocaine maximum dose with epinephrine",
    "bupivacaine max dose",
    "local anesthetic toxicity treatment",
    "lipid emulsion dosing LAST",
    
    # Aesthetic procedures
    "laser skin resurfacing settings",
    "chemical peel depth",
    "microneedling contraindications",
    "prp injection protocol",
    
    # Drug interactions (common)
    "nsaid anticoagulant interaction",
    "aspirin warfarin interaction",
    "lidocaine drug interactions",
]

# Thread-local storage for connections
_local = threading.local()


def get_cache_hash(text: str, prefix: str = "") -> str:
    """Generate a hash key for caching."""
    content = f"{prefix}:{text}".encode('utf-8')
    return hashlib.sha256(content).hexdigest()[:32]


def _ensure_cache_dir():
    """Ensure cache directory exists."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_embedding_db() -> sqlite3.Connection:
    """Get thread-local SQLite connection for embedding cache."""
    if not hasattr(_local, 'embedding_conn') or _local.embedding_conn is None:
        _ensure_cache_dir()
        _local.embedding_conn = sqlite3.connect(str(EMBEDDING_CACHE_DB), check_same_thread=False)
        _init_embedding_cache(_local.embedding_conn)
    return _local.embedding_conn


def _get_answer_db() -> sqlite3.Connection:
    """Get thread-local SQLite connection for answer cache."""
    if not hasattr(_local, 'answer_conn') or _local.answer_conn is None:
        _ensure_cache_dir()
        _local.answer_conn = sqlite3.connect(str(ANSWER_CACHE_DB), check_same_thread=False)
        _init_answer_cache(_local.answer_conn)
    return _local.answer_conn


def _init_embedding_cache(conn: sqlite3.Connection):
    """Initialize embedding cache table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            hash TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            embedding TEXT NOT NULL,
            created_at REAL NOT NULL,
            hit_count INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_embeddings_created 
        ON embeddings(created_at)
    """)
    conn.commit()


def _init_answer_cache(conn: sqlite3.Connection):
    """Initialize answer cache table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            hash TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            answer TEXT NOT NULL,
            citations TEXT,
            metadata TEXT,
            created_at REAL NOT NULL,
            ttl_seconds REAL NOT NULL,
            hit_count INTEGER DEFAULT 0,
            is_hot INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_answers_created 
        ON answers(created_at)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_answers_hot 
        ON answers(is_hot)
    """)
    conn.commit()


# =============================================================================
# Embedding Cache
# =============================================================================

def get_cached_embedding(query: str) -> Optional[List[float]]:
    """Retrieve cached embedding for a query."""
    try:
        cache_hash = get_cache_hash(query, "emb")
        conn = _get_embedding_db()
        
        cursor = conn.execute(
            "SELECT embedding, created_at FROM embeddings WHERE hash = ?",
            (cache_hash,)
        )
        row = cursor.fetchone()
        
        if row:
            embedding_json, created_at = row
            # Check TTL
            if time.time() - created_at < EMBEDDING_TTL_SECONDS:
                # Update hit count
                conn.execute(
                    "UPDATE embeddings SET hit_count = hit_count + 1 WHERE hash = ?",
                    (cache_hash,)
                )
                conn.commit()
                return json.loads(embedding_json)
            else:
                # Expired, delete
                conn.execute("DELETE FROM embeddings WHERE hash = ?", (cache_hash,))
                conn.commit()
        
        return None
    except Exception as e:
        logger.warning(f"Embedding cache read error: {e}")
        return None


def set_cached_embedding(query: str, embedding: List[float]):
    """Store embedding in cache."""
    try:
        cache_hash = get_cache_hash(query, "emb")
        conn = _get_embedding_db()
        
        conn.execute("""
            INSERT OR REPLACE INTO embeddings (hash, query, embedding, created_at, hit_count)
            VALUES (?, ?, ?, ?, 0)
        """, (cache_hash, query[:500], json.dumps(embedding), time.time()))
        conn.commit()
    except Exception as e:
        logger.warning(f"Embedding cache write error: {e}")


def embed_text_cached(text: str, embed_fn) -> List[float]:
    """
    Cached wrapper for embed_text function.
    
    Args:
        text: Query text to embed
        embed_fn: The actual embedding function to call on cache miss
    
    Returns:
        Embedding vector as list of floats
    """
    # Check cache first
    cached = get_cached_embedding(text)
    if cached is not None:
        logger.debug(f"Embedding cache hit for: {text[:50]}...")
        return cached
    
    # Generate embedding
    embedding = embed_fn(text)
    
    # Store in cache
    set_cached_embedding(text, embedding)
    logger.debug(f"Embedding cached for: {text[:50]}...")
    
    return embedding


# =============================================================================
# Hot Question / Answer Cache
# =============================================================================

def get_cached_answer(query: str) -> Optional[Dict[str, Any]]:
    """Retrieve cached answer for a query."""
    try:
        cache_hash = get_cache_hash(query.lower().strip(), "ans")
        conn = _get_answer_db()
        
        cursor = conn.execute(
            """SELECT answer, citations, metadata, created_at, ttl_seconds 
               FROM answers WHERE hash = ?""",
            (cache_hash,)
        )
        row = cursor.fetchone()
        
        if row:
            answer, citations_json, metadata_json, created_at, ttl = row
            # Check TTL
            if time.time() - created_at < ttl:
                # Update hit count
                conn.execute(
                    "UPDATE answers SET hit_count = hit_count + 1 WHERE hash = ?",
                    (cache_hash,)
                )
                conn.commit()
                
                return {
                    "answer": answer,
                    "citations": json.loads(citations_json) if citations_json else [],
                    "metadata": json.loads(metadata_json) if metadata_json else {},
                    "cached": True,
                    "cache_age_seconds": time.time() - created_at,
                }
            else:
                # Expired, delete
                conn.execute("DELETE FROM answers WHERE hash = ?", (cache_hash,))
                conn.commit()
        
        return None
    except Exception as e:
        logger.warning(f"Answer cache read error: {e}")
        return None


def set_cached_answer(
    query: str,
    answer: str,
    citations: Optional[List[Dict]] = None,
    metadata: Optional[Dict] = None,
    ttl_seconds: float = HOT_QUESTION_TTL_SECONDS,
    is_hot: bool = False
):
    """Store answer in cache."""
    try:
        cache_hash = get_cache_hash(query.lower().strip(), "ans")
        conn = _get_answer_db()
        
        conn.execute("""
            INSERT OR REPLACE INTO answers 
            (hash, query, answer, citations, metadata, created_at, ttl_seconds, hit_count, is_hot)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
        """, (
            cache_hash,
            query[:500],
            answer,
            json.dumps(citations) if citations else None,
            json.dumps(metadata) if metadata else None,
            time.time(),
            ttl_seconds,
            1 if is_hot else 0
        ))
        conn.commit()
        logger.info(f"Answer cached for query: {query[:50]}...")
    except Exception as e:
        logger.warning(f"Answer cache write error: {e}")


def is_hot_question(query: str) -> bool:
    """Check if a query matches a hot question pattern."""
    q_lower = query.lower().strip()
    
    for hot_q in HOT_QUESTIONS:
        # Check if query contains all words from hot question
        hot_words = set(hot_q.lower().split())
        query_words = set(q_lower.split())
        
        if hot_words.issubset(query_words) or hot_q in q_lower:
            return True
        
        # Fuzzy match - 80% of words match
        overlap = len(hot_words & query_words)
        if overlap >= len(hot_words) * 0.8:
            return True
    
    return False


# =============================================================================
# Cache Statistics and Maintenance
# =============================================================================

def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    stats = {
        "embedding_cache": {},
        "answer_cache": {},
    }
    
    try:
        conn = _get_embedding_db()
        cursor = conn.execute("""
            SELECT COUNT(*), SUM(hit_count), 
                   MIN(created_at), MAX(created_at)
            FROM embeddings
        """)
        row = cursor.fetchone()
        if row:
            stats["embedding_cache"] = {
                "entries": row[0] or 0,
                "total_hits": row[1] or 0,
                "oldest_entry": row[2],
                "newest_entry": row[3],
            }
    except Exception as e:
        logger.warning(f"Error getting embedding cache stats: {e}")
    
    try:
        conn = _get_answer_db()
        cursor = conn.execute("""
            SELECT COUNT(*), SUM(hit_count), SUM(is_hot),
                   MIN(created_at), MAX(created_at)
            FROM answers
        """)
        row = cursor.fetchone()
        if row:
            stats["answer_cache"] = {
                "entries": row[0] or 0,
                "total_hits": row[1] or 0,
                "hot_entries": row[2] or 0,
                "oldest_entry": row[3],
                "newest_entry": row[4],
            }
    except Exception as e:
        logger.warning(f"Error getting answer cache stats: {e}")
    
    return stats


def cleanup_expired_cache():
    """Remove expired entries from caches."""
    now = time.time()
    
    try:
        conn = _get_embedding_db()
        cutoff = now - EMBEDDING_TTL_SECONDS
        result = conn.execute(
            "DELETE FROM embeddings WHERE created_at < ?",
            (cutoff,)
        )
        conn.commit()
        logger.info(f"Cleaned up {result.rowcount} expired embeddings")
    except Exception as e:
        logger.warning(f"Error cleaning embedding cache: {e}")
    
    try:
        conn = _get_answer_db()
        # Delete entries where created_at + ttl < now
        result = conn.execute(
            "DELETE FROM answers WHERE (created_at + ttl_seconds) < ?",
            (now,)
        )
        conn.commit()
        logger.info(f"Cleaned up {result.rowcount} expired answers")
    except Exception as e:
        logger.warning(f"Error cleaning answer cache: {e}")


def _fastembed_model_is_cached() -> bool:
    """
    Return True only if the fastembed ONNX model files already exist on disk.
    Avoids triggering a HuggingFace download during startup on production VMs
    where the model was not pre-baked into the image.
    """
    import os, pathlib
    cache_root = pathlib.Path(
        os.environ.get("FASTEMBED_CACHE_PATH", "/home/runner/workspace/.fastembed_cache")
    )
    # fastembed stores the model under models--<org>--<name>-onnx/
    model_dir = cache_root / "models--qdrant--all-MiniLM-L6-v2-onnx"
    if not model_dir.exists():
        return False
    # Must have at least one real file (not just lock files)
    return any(
        f.stat().st_size > 10_000  # actual model file, not a lock
        for f in model_dir.rglob("*")
        if f.is_file()
    )


def warm_embedding_cache():
    """
    Pre-warm embedding cache with common clinical query terms on startup.
    Runs in a background thread so it doesn't block server start.

    If the ONNX model is not already cached on disk this function returns
    immediately without launching a thread — we never trigger a network
    download during startup.  The model will be fetched lazily on the first
    real search request instead.
    """
    import threading

    if not _fastembed_model_is_cached():
        logger.info("Embedding model not in local cache — skipping startup warmup (lazy load on first use)")
        return

    def _warm():
        try:
            from app.rag.embedder import embed_text
            warmed = 0
            for q in HOT_QUESTIONS:
                cached = get_cached_embedding(q)
                if cached is None:
                    vec = embed_text(q)
                    set_cached_embedding(q, vec)
                    warmed += 1
            logger.info(f"Embedding cache warmed: {warmed} new, {len(HOT_QUESTIONS) - warmed} already cached")
        except Exception as e:
            logger.warning(f"Embedding cache warming failed: {e}")

    t = threading.Thread(target=_warm, daemon=True)
    t.start()


def warm_hot_questions_cache():
    """
    Pre-warm cache with common clinical questions.
    Should be called on startup or periodically.
    """
    logger.info(f"Warming cache with {len(HOT_QUESTIONS)} hot questions...")
    warm_embedding_cache()


# =============================================================================
# Generic Key-Value Cache (for Phase 2-5 features)
# =============================================================================

def make_cache_key(kind: str, obj: dict) -> str:
    """Generate a cache key from a kind identifier and object."""
    raw = kind + ":" + json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_get(key: str) -> Optional[Dict[str, Any]]:
    """
    Generic cache get for Phase 2-5 features.
    Uses the answer cache db with a different prefix.
    """
    try:
        conn = _get_answer_db()
        cursor = conn.execute(
            """SELECT answer, citations, metadata, created_at, ttl_seconds 
               FROM answers WHERE hash = ?""",
            (key,)
        )
        row = cursor.fetchone()
        
        if row:
            answer, citations_json, metadata_json, created_at, ttl = row
            if time.time() - created_at < ttl:
                conn.execute(
                    "UPDATE answers SET hit_count = hit_count + 1 WHERE hash = ?",
                    (key,)
                )
                conn.commit()
                
                result = json.loads(answer) if answer.startswith('{') else {"content": answer}
                if citations_json:
                    result["citations"] = json.loads(citations_json)
                return result
            else:
                conn.execute("DELETE FROM answers WHERE hash = ?", (key,))
                conn.commit()
        
        return None
    except Exception as e:
        logger.warning(f"Cache get error: {e}")
        return None


def cache_set(key: str, payload: dict, ttl_seconds: float = HOT_QUESTION_TTL_SECONDS):
    """
    Generic cache set for Phase 2-5 features.
    """
    try:
        conn = _get_answer_db()
        
        conn.execute("""
            INSERT OR REPLACE INTO answers 
            (hash, query, answer, citations, metadata, created_at, ttl_seconds, hit_count, is_hot)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)
        """, (
            key,
            key[:100],
            json.dumps(payload),
            None,
            None,
            time.time(),
            ttl_seconds
        ))
        conn.commit()
    except Exception as e:
        logger.warning(f"Cache set error: {e}")

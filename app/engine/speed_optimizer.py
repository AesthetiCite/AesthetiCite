"""
AesthetiCite — Speed Optimizer
================================
Target: complication queries answered in < 2 seconds.

Three layers:
  1. HOT QUERY CACHE  — precomputed answers for the 20 most common
     complication queries. Served from memory in < 5ms.

  2. CONTEXT LIMITER  — caps evidence pack at 6 chunks for complication
     queries (vs 12 for general). Cuts LLM prompt tokens by ~50%.
     Less context = faster first token = better perceived speed.

  3. EMBEDDING PRECOMPUTE  — at startup, pre-embeds the 20 hot queries
     so the first real request skips the embedding step.

Exposed functions:
  is_hot_complication(query)         → bool
  get_hot_answer(query)              → cached answer dict or None
  set_hot_answer(query, result)      → None
  limit_context(chunks, query)       → trimmed chunk list
  precompute_hot_queries(retrieve_fn)→ None (call once at startup)
  get_speed_stats()                  → dict of cache hit counts
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ===========================================================================
# 1. HOT QUERY REGISTRY
# ===========================================================================

HOT_QUERIES: List[Dict[str, Any]] = [
    # VASCULAR OCCLUSION
    {"id": "vo_main",    "canonical": "vascular occlusion management hyaluronidase treatment protocol",
     "aliases": ["vascular occlusion", "occlusion filler", "blanching filler", "livedo filler",
                 "vascular compromise filler", "ischaemia filler"]},
    {"id": "vo_dose",    "canonical": "hyaluronidase dose vascular occlusion",
     "aliases": ["hyaluronidase dosing", "how much hyaluronidase", "hyaluronidase units occlusion"]},
    {"id": "vo_visual",  "canonical": "visual symptoms after filler emergency management",
     "aliases": ["vision loss filler", "blindness filler", "visual disturbance filler", "ophthalmology filler"]},

    # ANAPHYLAXIS
    {"id": "ana_main",   "canonical": "anaphylaxis emergency management aesthetic injectable",
     "aliases": ["anaphylaxis treatment", "anaphylactic reaction filler", "adrenaline dose anaphylaxis",
                 "allergic reaction injectable"]},

    # NODULES
    {"id": "nod_main",   "canonical": "filler nodule granuloma treatment management",
     "aliases": ["nodule after filler", "lump after filler", "granuloma filler",
                 "inflammatory nodule filler", "bump after filler"]},
    {"id": "nod_5fu",    "canonical": "5-FU triamcinolone filler nodule injection",
     "aliases": ["5fu filler nodule", "intralesional filler nodule"]},

    # INFECTION / BIOFILM
    {"id": "inf_main",   "canonical": "post-filler infection biofilm treatment antibiotics",
     "aliases": ["infection after filler", "biofilm filler", "abscess filler",
                 "cellulitis filler", "antibiotics filler infection"]},

    # PTOSIS
    {"id": "pto_main",   "canonical": "botulinum toxin induced ptosis management apraclonidine",
     "aliases": ["ptosis after botox", "eyelid drooping botox", "apraclonidine ptosis",
                 "brow drop botox"]},

    # TYNDALL
    {"id": "tyn_main",   "canonical": "tyndall effect filler hyaluronidase treatment",
     "aliases": ["tyndall effect", "blue filler under skin", "grey discolouration filler",
                 "superficial filler dissolve"]},

    # DIR
    {"id": "dir_main",   "canonical": "delayed inflammatory reaction filler management treatment",
     "aliases": ["delayed inflammatory reaction", "dir filler", "filler swelling weeks later",
                 "covid filler reaction"]},

    # NECROSIS
    {"id": "nec_main",   "canonical": "skin necrosis after filler management treatment",
     "aliases": ["necrosis filler", "tissue death filler", "black skin filler",
                 "eschar filler"]},

    # TECHNIQUE / DOSING
    {"id": "hyal_calc",  "canonical": "hyaluronidase dosing calculator regions",
     "aliases": ["how much hyaluronidase per region", "hyaluronidase dose lips",
                 "hyaluronidase dose tear trough"]},
    {"id": "botox_glab", "canonical": "botox dose glabellar lines units technique",
     "aliases": ["glabellar botox dose", "frown lines botox units", "glabella toxin injection"]},
    {"id": "lip_filler", "canonical": "lip filler technique safety vascular danger zones",
     "aliases": ["lip filler safety", "lip filler danger zones", "lip augmentation technique"]},
    {"id": "tear_trough","canonical": "tear trough filler technique safety periorbital",
     "aliases": ["tear trough injection", "infraorbital filler", "under eye filler technique"]},

    # PRE-PROCEDURE
    {"id": "prepro_vac", "canonical": "pre-procedure safety filler vascular occlusion prevention",
     "aliases": ["avoid vascular occlusion", "prevent occlusion filler", "pre-procedure safety"]},

    # DRUG INTERACTIONS
    {"id": "warfarin",   "canonical": "warfarin anticoagulant filler bruising safety",
     "aliases": ["warfarin filler", "anticoagulant filler", "blood thinners filler"]},
]


def _norm(q: str) -> str:
    return " ".join(q.lower().strip().split())


def _query_hash(q: str) -> str:
    return hashlib.md5(_norm(q).encode()).hexdigest()


_ALIAS_INDEX: Dict[str, str] = {}
for _hq in HOT_QUERIES:
    _ALIAS_INDEX[_norm(_hq["canonical"])] = _hq["canonical"]
    for _alias in _hq.get("aliases", []):
        _ALIAS_INDEX[_norm(_alias)] = _hq["canonical"]


def is_hot_complication(query: str) -> Tuple[bool, Optional[str]]:
    """Returns (is_hot, canonical_query)."""
    norm = _norm(query)

    if norm in _ALIAS_INDEX:
        return True, _ALIAS_INDEX[norm]

    for alias, canonical in _ALIAS_INDEX.items():
        if len(norm) < 40 and norm in alias:
            return True, canonical
        if len(alias) < 40 and alias in norm:
            return True, canonical

    return False, None


# ===========================================================================
# 2. IN-MEMORY HOT ANSWER CACHE
# ===========================================================================

class HotAnswerCache:
    def __init__(self, ttl_seconds: int = 3600):
        self._store: Dict[str, Tuple[float, Dict]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0

    def get(self, canonical: str) -> Optional[Dict]:
        key = _query_hash(canonical)
        with self._lock:
            entry = self._store.get(key)
            if entry:
                ts, val = entry
                if time.time() - ts < self._ttl:
                    self._hits += 1
                    return val
                del self._store[key]
            self._misses += 1
            return None

    def set(self, canonical: str, value: Dict) -> None:
        key = _query_hash(canonical)
        with self._lock:
            self._store[key] = (time.time(), value)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / max(total, 1)
            return {
                "cached_queries": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 3),
            }

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


_hot_cache = HotAnswerCache(ttl_seconds=3600)


def get_hot_answer(query: str) -> Optional[Dict]:
    direct = _hot_cache.get(_norm(query))
    if direct:
        return {**direct, "cache_source": "hot_direct"}

    _, canonical = is_hot_complication(query)
    if canonical:
        cached = _hot_cache.get(canonical)
        if cached:
            return {**cached, "cache_source": "hot_canonical"}

    return None


def set_hot_answer(query: str, result: Dict) -> None:
    _hot_cache.set(_norm(query), result)
    _, canonical = is_hot_complication(query)
    if canonical:
        _hot_cache.set(canonical, result)


# ===========================================================================
# 3. CONTEXT LIMITER
# ===========================================================================

CONTEXT_LIMITS = {
    "complication":          6,
    "high_risk_anatomy":     6,
    "technique":             8,
    "general":              10,
    "deepconsult":          14,
}

_COMPLICATION_KWS = frozenset([
    "vascular", "occlusion", "blanching", "livedo", "anaphylaxis",
    "adrenaline", "epinephrine", "hyaluronidase", "necrosis", "ischaemia",
    "ischemia", "ptosis", "nodule", "granuloma", "infection", "biofilm",
    "tyndall", "delayed inflammatory", "dir", "emergency", "complication",
])


def _detect_query_mode(query: str) -> str:
    q = query.lower()
    if any(kw in q for kw in _COMPLICATION_KWS):
        return "complication"
    if any(kw in q for kw in ("glabella", "temple", "tear trough", "periorbital", "nose", "lips")):
        return "high_risk_anatomy"
    if any(kw in q for kw in ("dose", "dosage", "units", "volume", "technique", "cannula")):
        return "technique"
    return "general"


def limit_context(
    chunks: List[Dict[str, Any]],
    query: str,
    mode: str = "auto",
    is_deepconsult: bool = False,
) -> List[Dict[str, Any]]:
    """
    Trim the evidence pack to the optimal size for the query type.
    Preserves evidence hierarchy — guidelines kept even if they'd be cut.
    """
    if is_deepconsult:
        return chunks

    if mode == "auto":
        mode = _detect_query_mode(query)

    limit = CONTEXT_LIMITS.get(mode, 10)

    if len(chunks) <= limit:
        return chunks

    priority = [c for c in chunks if (c.get("evidence_rank") or 99) <= 2]
    rest = [c for c in chunks if (c.get("evidence_rank") or 99) > 2]

    trimmed = priority + rest[:max(0, limit - len(priority))]
    return trimmed[:limit]


def estimated_prompt_tokens(chunks: List[Dict[str, Any]]) -> int:
    total_chars = sum(len(c.get("text", "") or c.get("chunk_text", "")) for c in chunks)
    return total_chars // 4


# ===========================================================================
# 4. STARTUP PRECOMPUTE
# ===========================================================================

def precompute_hot_queries(
    retrieve_fn: Callable[[str, int], List[Dict[str, Any]]],
    max_queries: int = 10,
    verbose: bool = True,
) -> None:
    """
    Pre-embed the top hot queries at startup so the first real request
    doesn't pay the embedding latency.

    Call this in app/main.py @startup after the retrieval pool is ready:
        from app.engine.speed_optimizer import precompute_hot_queries
        from app.rag.retriever import retrieve_db
        precompute_hot_queries(lambda q, k: retrieve_db(db, q, k=k))

    This does NOT precompute LLM answers (too expensive) — only retrieval.
    """

    def _run():
        done = 0
        for hq in HOT_QUERIES[:max_queries]:
            canonical = hq["canonical"]
            try:
                t0 = time.time()
                chunks = retrieve_fn(canonical, 8)
                elapsed = round((time.time() - t0) * 1000, 1)
                if verbose:
                    logger.info(
                        f"[speed_optimizer] precomputed '{canonical[:50]}' "
                        f"→ {len(chunks)} chunks in {elapsed}ms"
                    )
                done += 1
            except Exception as e:
                logger.warning(f"[speed_optimizer] precompute failed for '{canonical[:50]}': {e}")

        logger.info(f"[speed_optimizer] precomputed {done}/{max_queries} hot queries")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


# ===========================================================================
# 5. LATENCY TRACKER
# ===========================================================================

class LatencyTracker:
    def __init__(self, window: int = 100):
        self._data: Dict[str, List[float]] = {}
        self._window = window
        self._lock = threading.Lock()

    def record(self, mode: str, latency_ms: float) -> None:
        with self._lock:
            if mode not in self._data:
                self._data[mode] = []
            self._data[mode].append(latency_ms)
            if len(self._data[mode]) > self._window:
                self._data[mode].pop(0)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            result = {}
            for mode, times in self._data.items():
                if times:
                    result[mode] = {
                        "avg_ms": round(sum(times) / len(times), 1),
                        "p50_ms": round(sorted(times)[len(times) // 2], 1),
                        "p95_ms": round(sorted(times)[int(len(times) * 0.95)], 1),
                        "samples": len(times),
                        "target_met": sum(1 for t in times if t < 2000) / len(times),
                    }
            return result


_latency_tracker = LatencyTracker()


def record_latency(mode: str, latency_ms: float) -> None:
    _latency_tracker.record(mode, latency_ms)


def get_speed_stats() -> Dict[str, Any]:
    return {
        "hot_cache": _hot_cache.stats(),
        "latency": _latency_tracker.stats(),
        "hot_queries_registered": len(HOT_QUERIES),
    }

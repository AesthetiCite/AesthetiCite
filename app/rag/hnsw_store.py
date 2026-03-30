"""
HNSW ANN Index for sub-3s latency vector search.
Uses hnswlib for fast approximate nearest neighbor search.
Loads index from hnsw.bin and metadata from hnsw_meta.json.

Lazy-initialised: the module-level `hnsw_store` instance is only constructed
on first access, preventing OOM crashes at import time in constrained VMs.
"""
from __future__ import annotations
import os
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 384 matches sentence-transformers/all-MiniLM-L6-v2 (the actual model used)
EMBED_DIM = int(os.getenv("EMBED_DIM", "384"))
HNSW_INDEX_PATH = os.getenv("HNSW_INDEX_PATH", "./index/hnsw.bin")
HNSW_META_PATH = os.getenv("HNSW_META_PATH", "./index/hnsw_meta.json")
# Reduced from 200 000 — each slot is dim×4 bytes; 50 000×384×4 ≈ 75 MB
HNSW_MAX_ELEMENTS = int(os.getenv("HNSW_MAX_ELEMENTS", "50000"))
HNSW_M = int(os.getenv("HNSW_M", "16"))
HNSW_EF = int(os.getenv("HNSW_EF", "128"))


def _hnswlib_safe() -> bool:
    """Test hnswlib in a subprocess — catches SIGILL / AVX2 crashes."""
    import subprocess, sys  # nosec B404
    try:
        r = subprocess.run(  # nosec B603
            [sys.executable, "-c", "import hnswlib; hnswlib.Index('cosine', 2)"],
            timeout=8, capture_output=True,
        )
        return r.returncode == 0
    except Exception:
        return False


hnswlib = None
HNSWLIB_AVAILABLE = False
if _hnswlib_safe():
    try:
        import hnswlib
        HNSWLIB_AVAILABLE = True
    except Exception:  # nosec B110
        pass

if not HNSWLIB_AVAILABLE:
    logger.warning("hnswlib not available (missing or CPU incompatible) — falling back to pgvector")


class HNSWStore:
    """HNSW index for fast approximate nearest neighbor search."""

    def __init__(self, dim: int = EMBED_DIM):
        self.dim = dim
        self.ok = False
        self.idx = None
        self.id_to_chunk: Dict[int, dict] = {}
        self.by_hash: Dict[str, dict] = {}
        self.id_to_hash: Dict[int, str] = {}
        self.next_id = 0

        if not HNSWLIB_AVAILABLE:
            logger.warning("hnswlib not available - HNSW store disabled")
            return

        try:
            self.idx = hnswlib.Index(space="cosine", dim=dim)

            if os.path.exists(HNSW_INDEX_PATH):
                self.idx.load_index(HNSW_INDEX_PATH)
                self._load_meta()
                logger.info(f"Loaded HNSW index from {HNSW_INDEX_PATH} ({self.next_id} vectors)")
            else:
                self.idx.init_index(
                    max_elements=HNSW_MAX_ELEMENTS,
                    ef_construction=200,
                    M=HNSW_M
                )
                logger.info(f"Initialized new HNSW index (dim={dim}, max={HNSW_MAX_ELEMENTS})")

            self.idx.set_ef(HNSW_EF)
            self.ok = True
        except Exception as e:
            logger.error(f"Failed to initialize HNSW: {e}")
            self.ok = False

    def _load_meta(self):
        """Load metadata from hnsw_meta.json."""
        if not os.path.exists(HNSW_META_PATH):
            logger.warning(f"No meta file at {HNSW_META_PATH}")
            return

        try:
            with open(HNSW_META_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.by_hash = data.get("by_hash", {})
            raw_id_to_hash = data.get("id_to_hash", {})
            self.id_to_hash = {int(k): v for k, v in raw_id_to_hash.items()}

            for label, h in self.id_to_hash.items():
                if h in self.by_hash:
                    self.id_to_chunk[label] = self.by_hash[h]

            self.next_id = max(self.id_to_hash.keys()) + 1 if self.id_to_hash else 0
            logger.info(f"Loaded {len(self.id_to_chunk)} chunk metas from {HNSW_META_PATH}")
        except Exception as e:
            logger.error(f"Failed to load meta: {e}")

    def add(self, embedding: List[float], chunk: dict) -> int:
        """Add a chunk with its embedding to the index."""
        if not self.ok or self.idx is None:
            return -1

        try:
            i = self.next_id
            self.idx.add_items([embedding], [i])
            self.id_to_chunk[i] = chunk
            self.next_id += 1
            return i
        except Exception as e:
            logger.error(f"HNSW add error: {e}")
            return -1

    def add_batch(self, embeddings: List[List[float]], chunks: List[dict]) -> int:
        """Add multiple chunks at once."""
        if not self.ok or self.idx is None:
            return 0

        added = 0
        for emb, chunk in zip(embeddings, chunks):
            if self.add(emb, chunk) >= 0:
                added += 1
        return added

    def search(self, embedding: List[float], k: int = 12) -> List[dict]:
        """Search for k nearest neighbors. Returns chunk metadata with text."""
        if not self.ok or self.idx is None or self.next_id == 0:
            return []

        try:
            labels, distances = self.idx.knn_query([embedding], k=min(k, self.next_id))
            results = []
            for lab, dist in zip(labels[0], distances[0]):
                chunk = self.id_to_chunk.get(int(lab))
                if chunk:
                    results.append({
                        "text": chunk.get("text", ""),
                        "title": chunk.get("title", ""),
                        "source_type": chunk.get("source_type", "other"),
                        "url": chunk.get("url") or chunk.get("doi") or "",
                        "year": chunk.get("year"),
                        "source_path": chunk.get("source_path", ""),
                        "_hnsw_distance": float(dist),
                        "_score": 1.0 - float(dist),
                    })
            return results
        except Exception as e:
            logger.error(f"HNSW search error: {e}")
            return []

    def save(self) -> bool:
        """Save the index to disk."""
        if not self.ok or self.idx is None:
            return False

        try:
            self.idx.save_index(HNSW_INDEX_PATH)
            logger.info(f"Saved HNSW index to {HNSW_INDEX_PATH}")
            return True
        except Exception as e:
            logger.error(f"HNSW save error: {e}")
            return False

    @property
    def count(self) -> int:
        return self.next_id


# ---------------------------------------------------------------------------
# Lazy singleton — only constructed on first access.
# This prevents the 1.2 GB init_index() allocation from happening at module
# import time, which caused OOM kills in constrained deployment VMs.
# ---------------------------------------------------------------------------
_hnsw_store_instance: Optional[HNSWStore] = None


def _get_hnsw_store() -> HNSWStore:
    global _hnsw_store_instance
    if _hnsw_store_instance is None:
        _hnsw_store_instance = HNSWStore()
    return _hnsw_store_instance


class _LazyHNSWStore:
    """Proxy that instantiates HNSWStore on first attribute access."""

    def __getattr__(self, name: str):
        return getattr(_get_hnsw_store(), name)

    def __bool__(self) -> bool:
        return _get_hnsw_store().ok


hnsw_store = _LazyHNSWStore()

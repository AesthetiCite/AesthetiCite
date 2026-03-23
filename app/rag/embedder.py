from __future__ import annotations
from functools import lru_cache
from typing import List
from fastembed import TextEmbedding
import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    return TextEmbedding(model_name=MODEL_NAME)

def embed_text(text: str) -> list[float]:
    """
    Returns a 384-dim normalized embedding as list[float] compatible with pgvector.
    Uses fastembed with ONNX backend (no torch required).
    """
    m = _model()
    embeddings = list(m.embed([text]))
    vec = embeddings[0]
    return [float(x) for x in np.asarray(vec, dtype=np.float32).tolist()]


def embed_texts_batch(texts: List[str], batch_size: int = 16) -> List[list[float]]:
    """
    Batch-embed multiple texts efficiently. Yields one embedding per input text.
    Processes in mini-batches to control memory usage.
    """
    m = _model()
    results: List[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        vecs = list(m.embed(batch))
        for vec in vecs:
            results.append([float(x) for x in np.asarray(vec, dtype=np.float32).tolist()])
    return results

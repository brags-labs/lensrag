from __future__ import annotations
import numpy as np

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class DenseEncoder:
    """Sentence-transformers adapter. Model is pinned by name; downloads on first use."""
    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError("Dense embeddings require: pip install sentence-transformers") from e
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def encode(self, texts, batch_size=64):
        return np.asarray(self.model.encode(list(texts), batch_size=batch_size, normalize_embeddings=True,
                                            convert_to_numpy=True, show_progress_bar=False), dtype=np.float32)

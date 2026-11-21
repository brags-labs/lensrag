from __future__ import annotations
import numpy as np

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MAX_SEQ_LENGTH = 1024


class DenseEncoder:
    """Sentence-transformers adapter. Model is pinned by name; downloads on first use."""
    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError("Dense embeddings require: pip install sentence-transformers") from e
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        # LensRAG chunks are a few hundred tokens; long-context embedders (BGE-M3 accepts 8,192) would
        # otherwise size every batch for their maximum and can exhaust GPU memory shared with local LLMs.
        if getattr(self.model, "max_seq_length", 0) and self.model.max_seq_length > MAX_SEQ_LENGTH:
            self.model.max_seq_length = MAX_SEQ_LENGTH

    def encode(self, texts, batch_size=16):
        return np.asarray(self.model.encode(list(texts), batch_size=batch_size, normalize_embeddings=True,
                                            convert_to_numpy=True, show_progress_bar=False), dtype=np.float32)

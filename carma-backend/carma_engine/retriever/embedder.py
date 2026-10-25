"""
Embeddings + corpus access for the CAR retriever.

``BGEEmbedder``      the planned configuration: BAAI/bge-base-en-v1.5 embeddings
                     stored in Qdrant.
``HashingEmbedder``  a deterministic, dependency-free fallback used when
                     sentence-transformers / Qdrant are unavailable.  It hashes
                     word unigrams+bigrams into a fixed-width vector, so the
                     cosine similarity is a real (lexical) similarity score and
                     the alpha/beta/gamma formula keeps its meaning.

The corpus itself lives in the database (``processes.CorpusDocument``); the
Qdrant collection is a materialised index over it.  Keeping the corpus in the
database means the retrievable knowledge is versioned, auditable and exportable
with the rest of the research artifact.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections import Counter

import numpy as np

log = logging.getLogger('carma')

DEFAULT_MODEL = 'BAAI/bge-base-en-v1.5'
DEFAULT_COLLECTION = 'carma_corpus'
FALLBACK_DIM = 256
_TOKEN_RE = re.compile(r'[a-z0-9]+')


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or '').lower())


class HashingEmbedder:
    """Deterministic hashed bag-of-ngrams embedder (L2-normalised)."""

    dimension = FALLBACK_DIM

    def __init__(self, dimension: int = FALLBACK_DIM):
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        vector = np.zeros(self.dimension, dtype=float)
        tokens = _tokens(text)
        if not tokens:
            return vector.tolist()
        features = Counter(tokens)
        features.update(f'{a}_{b}' for a, b in zip(tokens, tokens[1:]))
        for feature, count in features.items():
            digest = hashlib.blake2b(feature.encode('utf-8'), digest_size=8).digest()
            index = int.from_bytes(digest[:4], 'big') % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign * (1.0 + np.log(count))
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector /= norm
        return vector.tolist()


class BGEEmbedder:
    """Sentence-transformers embeddings + Qdrant storage."""

    def __init__(self, model_name: str = DEFAULT_MODEL,
                 collection: str = DEFAULT_COLLECTION,
                 qdrant_url: str | None = None,
                 qdrant_api_key: str | None = None):
        from django.conf import settings  # noqa: PLC0415
        from qdrant_client import QdrantClient  # noqa: PLC0415
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        self.model_name = model_name
        self.collection = collection
        self.model = SentenceTransformer(model_name)
        self.qdrant = QdrantClient(
            url=qdrant_url or settings.QDRANT_URL,
            api_key=qdrant_api_key or settings.QDRANT_API_KEY or None,
        )
        self.dimension = self.model.get_sentence_embedding_dimension()
        self._corpus_cache: dict[str, list] = {}
        self._ensure_collection()

    def _ensure_collection(self):
        from qdrant_client.models import Distance, VectorParams  # noqa: PLC0415
        existing = {c.name for c in self.qdrant.get_collections().collections}
        if self.collection not in existing:
            self.qdrant.create_collection(
                self.collection,
                vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
            )
            log.info('Created Qdrant collection "%s" (dim=%d).', self.collection, self.dimension)

    def embed(self, text: str) -> list[float]:
        return self.model.encode(text, normalize_embeddings=True).tolist()

    def upsert(self, doc_id: str, text: str, payload: dict):
        from qdrant_client.models import PointStruct  # noqa: PLC0415
        point_id = _point_id(doc_id)
        self.qdrant.upsert(
            self.collection,
            points=[PointStruct(id=point_id, vector=self.embed(text), payload=payload)],
        )

    def index_documents(self, documents, batch_size: int = 64) -> int:
        """Embed ``processes.CorpusDocument`` rows and upsert them into the index."""
        from qdrant_client.models import PointStruct  # noqa: PLC0415

        documents = list(documents)
        for start in range(0, len(documents), batch_size):
            batch = documents[start:start + batch_size]
            payloads = [document_to_payload(document) for document in batch]
            vectors = self.model.encode(
                [f"{payload['title']}\n{payload['content']}" for payload in payloads],
                normalize_embeddings=True, batch_size=32)
            self.qdrant.upsert(self.collection, points=[
                PointStruct(id=_point_id(payload['doc_id']), vector=vector.tolist(),
                            payload=payload)
                for payload, vector in zip(payloads, vectors)
            ])
        return len(documents)

    def corpus(self, process_id: str | None = None) -> list[dict]:
        """
        Every indexed document of a process, with its stored vector.

        Cached per process: the corpus is fixed while experiments run
        (restart the workers after ``index_corpus``).
        """
        key = str(process_id or '')
        if key not in self._corpus_cache:
            points, offset = [], None
            while True:
                batch, offset = self.qdrant.scroll(
                    self.collection, scroll_filter=_process_filter(process_id),
                    with_payload=True, with_vectors=True, limit=256, offset=offset)
                points.extend(batch)
                if offset is None:
                    break
            self._corpus_cache[key] = [
                {'id': (p.payload or {}).get('doc_id', str(p.id)),
                 'payload': p.payload or {}, 'embedding': list(p.vector or [])}
                for p in points
            ]
        return self._corpus_cache[key]

    def count(self, process_id: str | None = None) -> int:
        return self.qdrant.count(self.collection, count_filter=_process_filter(process_id),
                                 exact=True).count

    def search(self, query: str, limit: int = 50, process_id: str | None = None) -> list[dict]:
        """Dense top-``limit`` documents, with their stored vectors."""
        results = self.qdrant.query_points(
            collection_name=self.collection,
            query=self.embed(query),
            query_filter=_process_filter(process_id),
            limit=limit,
            with_payload=True,
            with_vectors=True,
        ).points
        return [{'id': (p.payload or {}).get('doc_id', str(p.id)), 'score': float(p.score),
                 'payload': p.payload or {}, 'embedding': list(p.vector or [])}
                for p in results]


def _process_filter(process_id: str | None):
    if not process_id:
        return None
    from qdrant_client.models import FieldCondition, Filter, MatchValue  # noqa: PLC0415

    return Filter(must=[FieldCondition(key='process_id', match=MatchValue(value=str(process_id)))])


def _point_id(doc_id: str) -> str:
    """Qdrant point IDs must be UUIDs or unsigned integers."""
    try:
        return str(uuid.UUID(str(doc_id)))
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, str(doc_id)))


_embedder_cache: dict = {}


def get_embedder(force_fallback: bool = False):
    """
    Return the configured embedder.

    Falls back to :class:`HashingEmbedder` when sentence-transformers or
    Qdrant are not reachable.  The fallback is deterministic, so a run stays
    reproducible.
    """
    if force_fallback:
        return HashingEmbedder()
    if 'embedder' in _embedder_cache:
        return _embedder_cache['embedder']
    try:
        embedder = BGEEmbedder()
        _embedder_cache['embedder'] = embedder
    except Exception as exc:
        log.warning('Falling back to hashing embedder (%s).', exc)
        embedder = HashingEmbedder()
        _embedder_cache['embedder'] = embedder
    return embedder


def document_to_payload(document) -> dict:
    """Convert a ``processes.CorpusDocument`` into a retriever payload."""
    metadata = dict(document.metadata or {})
    return {
        'doc_id': str(document.id),
        'title': document.title,
        'content': document.content,
        'doc_type': document.doc_type,
        'stage_tags': [document.stage] if document.stage else list(metadata.get('stage_tags') or []),
        'activity_tags': list(metadata.get('activity_tags') or []),
        'role_tags': list(metadata.get('role_tags') or []),
        'valid_from': document.metadata.get('valid_from') if document.metadata else None,
        'valid_until': document.metadata.get('valid_until') if document.metadata else None,
        'process_id': str(document.process_id) if document.process_id else None,
    }

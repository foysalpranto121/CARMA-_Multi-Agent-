"""
Constraint-Aware Retriever (CAR) and the plain vector-RAG baseline.

CAR pipeline
------------
1. **Recall**   candidates for the process corpus.  The corpus of record is the
   database (``processes.CorpusDocument``); when Qdrant is available the
   documents are materialised into a vector index and the dense top-k is
   merged with the database candidates so the retrievable set is never
   silently empty.
2. **Filter**   drop candidates that are not valid for the case timestamp,
   the current stage, or the currently enabled activities
   (:func:`~carma_engine.retriever.scorer.is_candidate_valid`).
3. **Rescore**  apply the composite score alpha*sim + beta*prox + gamma*match.
4. **Select**   return the top-k documents with a stable provenance id that
   the planner must cite in its plan.
"""
from __future__ import annotations

import logging

from .embedder import document_to_payload, get_embedder
from .scorer import cosine_sim, is_candidate_valid, score_candidate

log = logging.getLogger('carma')

DEFAULT_TOP_K = 10
RECALL_MULTIPLIER = 5
MAX_CANDIDATES = 200


def _provenance_id(doc_id: str) -> str:
    return f'PRV-{str(doc_id)[:8].upper()}'


class ConstraintAwareRetriever:
    """
    Constraint-aware retrieval over the process corpus.

    :param embedder:   embedder instance (defaults to the configured one)
    :param alpha:      weight of the dense similarity term
    :param beta:       weight of the graph-proximity term
    :param gamma:      weight of the stage/temporal match term
    """

    def __init__(self, embedder=None, alpha: float = 0.6, beta: float = 0.2,
                 gamma: float = 0.2, process_id: str | None = None):
        self.embedder = embedder or get_embedder()
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.process_id = process_id

    # ── corpus access ─────────────────────────────────────────
    def _corpus_documents(self, process_id: str | None):
        from apps.processes.models import CorpusDocument  # noqa: PLC0415
        queryset = CorpusDocument.objects.all()
        if process_id:
            queryset = queryset.filter(process_id=process_id)
        return queryset[:MAX_CANDIDATES]

    def _candidates(self, process_id: str | None, query: str) -> list[dict]:
        candidates = []
        for document in self._corpus_documents(process_id):
            payload = document_to_payload(document)
            candidates.append({
                'id': payload['doc_id'],
                'payload': payload,
                'embedding': self.embedder.embed(f"{payload['title']}\n{payload['content']}"),
            })
        return candidates

    # ── public API ────────────────────────────────────────────
    def retrieve(self, query: str, state, constraint_graph=None,
                 case_timestamp=None, process_id: str | None = None,
                 k: int = DEFAULT_TOP_K) -> list[dict]:
        """
        Retrieve the ``k`` best constraint-valid documents.

        :param query:            natural-language query built from the case
        :param state:            a :class:`~carma_engine.state_estimator.replay.ProcessState`
        :param constraint_graph: compiled constraint graph (for proximity)
        :param case_timestamp:   timestamp of the case (temporal validity)
        :param process_id:       restrict the corpus to one process
        :param k:                number of documents to return
        """
        process_id = process_id or self.process_id
        candidates = self._candidates(process_id, query)
        if not candidates:
            return []

        query_embedding = self.embedder.embed(query)

        valid = [c for c in candidates
                 if is_candidate_valid(c['payload'], state, case_timestamp)]

        scored = []
        for candidate in valid:
            score = score_candidate(
                query_embedding=query_embedding,
                doc_embedding=candidate['embedding'],
                doc_payload=candidate['payload'],
                state=state,
                graph=constraint_graph,
                alpha=self.alpha,
                beta=self.beta,
                gamma=self.gamma,
            )
            scored.append({
                'id': candidate['id'],
                'payload': candidate['payload'],
                'score': score,
                'similarity': cosine_sim(query_embedding, candidate['embedding']),
                'provenance_id': _provenance_id(candidate['id']),
            })

        scored.sort(key=lambda item: item['score'], reverse=True)
        return scored[:k]

    def retrieve_precedents(self, prefix: list, process_id: str | None = None,
                            k: int = 3) -> list[dict]:
        """Case-based precedent retrieval (historical cases in the corpus)."""
        activities = [e.get('activity', '') for e in (prefix or [])][-5:]
        query = 'precedent ' + ' '.join(activities)
        candidates = self._candidates(process_id, query)
        query_embedding = self.embedder.embed(query)
        precedents = [c for c in candidates
                      if c['payload'].get('doc_type') in ('case', 'precedent')]
        for candidate in precedents:
            candidate['similarity'] = cosine_sim(query_embedding, candidate['embedding'])
            candidate['provenance_id'] = _provenance_id(candidate['id'])
        precedents.sort(key=lambda item: item['similarity'], reverse=True)
        return precedents[:k]


def plain_vector_rag(process_id: str | None, query: str,
                     k: int = DEFAULT_TOP_K, embedder=None) -> list[dict]:
    """
    Baseline retriever used by B2 / B4: dense similarity only, with no
    constraint filtering and no graph-proximity re-ranking.
    """
    retriever = ConstraintAwareRetriever(embedder=embedder, alpha=1.0, beta=0.0, gamma=0.0)
    candidates = retriever._candidates(process_id, query)
    if not candidates:
        return []
    query_embedding = retriever.embedder.embed(query)
    scored = []
    for candidate in candidates:
        similarity = cosine_sim(query_embedding, candidate['embedding'])
        scored.append({
            'id': candidate['id'],
            'payload': candidate['payload'],
            'score': similarity,
            'similarity': similarity,
            'provenance_id': _provenance_id(candidate['id']),
        })
    scored.sort(key=lambda item: item['score'], reverse=True)
    return scored[:k]

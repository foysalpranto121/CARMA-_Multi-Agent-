"""Constraint-Aware Retrieval (CAR) — retriever, scorer and corpus access."""

from .constraint_aware import ConstraintAwareRetriever, plain_vector_rag
from .embedder import get_embedder
from .scorer import (
    cosine_sim,
    graph_proximity,
    is_candidate_valid,
    score_candidate,
    stage_constraint_match,
)

__all__ = [
    'ConstraintAwareRetriever',
    'plain_vector_rag',
    'get_embedder',
    'cosine_sim',
    'graph_proximity',
    'stage_constraint_match',
    'score_candidate',
    'is_candidate_valid',
]

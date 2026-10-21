"""
Scoring functions for the Constraint-Aware Retriever.

Composite score (plan, Day 2 Block 2):

    score(d) = alpha * sim(query, d)      dense semantic similarity
             + beta  * prox(state, d)     graph proximity to the current node
             + gamma * match(state, d)    stage / temporal constraint match

``alpha + beta + gamma == 1`` keeps the score in ``[0, 1]`` so that
``retrieval_precision_at_k`` and the score thresholds stay interpretable.
"""
from __future__ import annotations

import networkx as nx
import numpy as np


def cosine_sim(a, b) -> float:
    """Cosine similarity between two vectors (0.0 when either is empty)."""
    a_arr, b_arr = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a_arr.size == 0 or b_arr.size == 0 or a_arr.shape != b_arr.shape:
        return 0.0
    denominator = (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)) + 1e-9
    return float(np.dot(a_arr, b_arr) / denominator)


def graph_proximity(graph: nx.DiGraph, current_node: str, activity_tags: list) -> float:
    """
    Proximity of the document's tagged activities to the current process node.

    ``1 / (1 + shortest_path_length)`` for the closest reachable tag; 0 when
    the tag is unreachable or absent from the graph.
    """
    if graph is None or not current_node or not activity_tags:
        return 0.0
    scores = []
    for tag in activity_tags:
        if not tag:
            continue
        try:
            length = nx.shortest_path_length(graph, current_node, tag)
            scores.append(1.0 / (1.0 + length))
        except (nx.NodeNotFound, nx.NetworkXNoPath, nx.NetworkXError):
            scores.append(0.0)
    return max(scores) if scores else 0.0


def stage_constraint_match(state, payload: dict) -> float:
    """1.0 when the document is applicable in the current stage, 0.5 when the
    document is stage-agnostic, 0.0 when it does not apply."""
    stage_tags = payload.get('stage_tags') or []
    if not stage_tags:
        return 0.5
    stage = getattr(state, 'stage', None) if not isinstance(state, dict) else state.get('stage')
    return 1.0 if stage in stage_tags else 0.0


def score_candidate(query_embedding, doc_embedding, doc_payload: dict,
                    state, graph, alpha: float, beta: float, gamma: float) -> float:
    """Composite CAR score for one candidate document."""
    similarity = cosine_sim(query_embedding, doc_embedding)
    current_node = getattr(state, 'current_node', '') if not isinstance(state, dict) \
        else state.get('current_node', '')
    proximity = graph_proximity(graph, current_node, doc_payload.get('activity_tags') or [])
    match = stage_constraint_match(state, doc_payload)
    return float(alpha * similarity + beta * proximity + gamma * match)


def is_candidate_valid(payload: dict, state, case_timestamp) -> bool:
    """
    Hard filter applied before scoring.

    A candidate is kept only if it is valid for the case timestamp, applicable
    in the current stage, and applicable to the activities of the case: it
    either talks about an activity that may happen next or about the activity
    the case is currently in.
    """
    payload = payload or {}
    stage = getattr(state, 'stage', None) if not isinstance(state, dict) else state.get('stage')
    enabled = (getattr(state, 'enabled_activities', None) if not isinstance(state, dict)
               else state.get('enabled_activities')) or []

    valid_from = payload.get('valid_from')
    valid_until = payload.get('valid_until')
    if case_timestamp is not None:
        if valid_from is not None and valid_from > case_timestamp:
            return False
        if valid_until is not None and valid_until <= case_timestamp:
            return False

    stage_tags = payload.get('stage_tags') or []
    if stage_tags and stage not in stage_tags:
        return False

    activity_tags = payload.get('activity_tags') or []
    if activity_tags and enabled:
        applicable = any(tag in enabled for tag in activity_tags)
        if not applicable and stage not in activity_tags:
            return False

    return True

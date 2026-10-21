"""B3 — Single LLM with GraphRAG (graph-proximity retrieval, no constraint filter)."""
from .base import BaseRunner


class B3GraphRAGRunner(BaseRunner):
    code = 'B3'
    retrieval_type = 'graph'
    multi_agent = False
    use_scv = False
    num_agents = 1

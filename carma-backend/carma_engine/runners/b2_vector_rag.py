"""B2 — Single LLM with plain vector RAG."""
from .base import BaseRunner


class B2VectorRAGRunner(BaseRunner):
    code = 'B2'
    retrieval_type = 'vector'
    multi_agent = False
    use_scv = False
    num_agents = 1

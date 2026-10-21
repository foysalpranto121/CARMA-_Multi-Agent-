"""B4 — Multi-agent system with plain vector RAG."""
from .base import BaseRunner


class B4MASVectorRunner(BaseRunner):
    code = 'B4'
    retrieval_type = 'vector'
    multi_agent = True
    use_scv = False
    num_agents = 4

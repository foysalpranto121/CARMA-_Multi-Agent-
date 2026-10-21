"""B6 — Multi-agent system with vector RAG and the Symbolic Constraint Verifier."""
from .base import BaseRunner


class B6MASSCVRunner(BaseRunner):
    code = 'B6'
    retrieval_type = 'vector'
    multi_agent = True
    use_scv = True
    num_agents = 4

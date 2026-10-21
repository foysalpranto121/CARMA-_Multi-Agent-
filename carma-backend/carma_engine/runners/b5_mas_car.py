"""B5 — Multi-agent system with the Constraint-Aware Retriever."""
from .base import BaseRunner


class B5MASCARRunner(BaseRunner):
    code = 'B5'
    retrieval_type = 'constraint_aware'
    multi_agent = True
    use_scv = False
    num_agents = 4

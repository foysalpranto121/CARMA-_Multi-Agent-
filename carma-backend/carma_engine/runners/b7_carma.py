"""B7 — CARMA full: Constraint-Aware Retrieval + Symbolic Constraint Verification."""
from .base import BaseRunner


class B7CARMARunner(BaseRunner):
    code = 'B7'
    retrieval_type = 'constraint_aware'
    multi_agent = True
    use_scv = True
    num_agents = 4

"""B1 — Single LLM, no retrieval, no SCV."""
from .base import BaseRunner


class B1SingleLLMRunner(BaseRunner):
    code = 'B1'
    retrieval_type = 'none'
    multi_agent = False
    use_scv = False
    num_agents = 1

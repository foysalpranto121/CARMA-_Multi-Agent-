"""
CARMA Engine — the AI core of the research platform.

Layering (matches the sprint plan, Day 2):

    constraint_knowledge/  compile a process frame F = (M, D, P) into an
                           executable constraint graph
    state_estimator/       estimate the current process state from a prefix trace
    retriever/             Constraint-Aware Retrieval (CAR): dense recall filtered
                           by stage / timestamp validity / reachability, then
                           rescored with alpha*sim + beta*prox + gamma*match
    agents/                LangGraph agent team (coordinator -> planner -> critic
                           -> executor) with evidence citation and repair loop
    verifier/              Symbolic Constraint Verifier (SCV): alignment, Declare
                           automata, policy predicates, cross-agent conflicts
    escalation/            confidence-gated escalation to a human reviewer
    runners/               B0..B7 experiment configurations

Every heavy third-party dependency (pm4py, qdrant, sentence-transformers,
langgraph, ...) is imported lazily so the package can be imported, unit-tested
and run in degraded mode without the full stack installed.
"""

__version__ = '1.0.0'

__all__ = [
    'constraint_knowledge',
    'state_estimator',
    'retriever',
    'agents',
    'verifier',
    'escalation',
    'runners',
]

"""
LangGraph wiring for the CARMA agent team.

    coordinator → planner → critic ─┬─(goal reachable)──→ executor → END
                                     └─(repair needed)──→ planner

The repair edge is bounded by ``k_repair_rounds`` so the graph always
terminates; exceeding the budget escalates the case to a human reviewer
instead of looping.
"""
from __future__ import annotations

import logging

log = logging.getLogger('carma')

DEFAULT_REPAIR_ROUNDS = 3


def build_agent_graph(llm=None, config=None, tau: float = 0.5,
                      agent_roles: list[str] | None = None,
                      repair_rounds: int = DEFAULT_REPAIR_ROUNDS):
    """
    Compile the agent graph.

    :param llm:          an :class:`~carma_engine.llm.client.LLMClient` (or ``None``
                        for the deterministic fallback path)
    :param config:       a ``RunConfiguration`` (only ``k_repair_rounds`` is used)
    :param tau:          confidence threshold below which the case escalates
    :param agent_roles:  specialist roles for the multi-agent configuration
    :param repair_rounds: maximum number of planner repair rounds
    """
    from langgraph.graph import END, START, StateGraph  # noqa: PLC0415

    from .coordinator import coordinator_node  # noqa: PLC0415
    from .critic import critic_node  # noqa: PLC0415
    from .executor import executor_node  # noqa: PLC0415
    from .planner import planner_node  # noqa: PLC0415
    from .schemas import AgentState  # noqa: PLC0415

    max_repairs = repair_rounds
    if config is not None:
        max_repairs = int(getattr(config, 'k_repair_rounds', repair_rounds) or repair_rounds)

    graph = StateGraph(AgentState)
    graph.add_node('coordinator', coordinator_node(llm, agent_roles))
    graph.add_node('planner', planner_node(llm))
    graph.add_node('critic', critic_node(llm, tau=tau))
    graph.add_node('executor', executor_node(llm, config))

    graph.add_edge(START, 'coordinator')
    graph.add_edge('coordinator', 'planner')
    graph.add_edge('planner', 'critic')
    graph.add_edge('executor', END)

    def route_after_critic(state: dict) -> str:
        review = (state.get('extras') or {}).get('critic') or {}
        if review.get('goal_reachable', True):
            return 'executor'
        if int(state.get('repair_round', 0)) < max_repairs:
            return 'planner'
        state['escalate'] = True
        state['escalation_reason'] = (
            (state.get('escalation_reason') or '') + 'Repair budget exhausted.').strip()
        return 'executor'

    graph.add_conditional_edges(
        'critic',
        route_after_critic,
        {'executor': 'executor', 'planner': 'planner'},
    )

    return graph.compile()

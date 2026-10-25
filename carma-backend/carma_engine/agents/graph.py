"""
LangGraph wiring for the CARMA agent team.

Multi-agent team (B4-B7)::

    coordinator → planner → critic ─┬─(goal reachable / declined)──→ executor → END
                                     └─(repair needed)─────────────→ planner

Single agent (B1-B3)::

    planner → executor → END

The repair edge is bounded by ``k_repair_rounds`` so the graph always
terminates; exceeding the budget flags the case for escalation instead of
looping.  Flags are set by the nodes, never by the router: LangGraph only
keeps the state a node returns.
"""
from __future__ import annotations

import logging

log = logging.getLogger('carma')

DEFAULT_REPAIR_ROUNDS = 3


def build_agent_graph(llm=None, config=None, tau: float = 0.5,
                      agent_roles: list[str] | None = None,
                      repair_rounds: int = DEFAULT_REPAIR_ROUNDS,
                      multi_agent: bool = True):
    """
    Compile the agent graph.

    :param llm:          an :class:`~carma_engine.llm.client.LLMClient` (or ``None``
                        for the deterministic fallback path)
    :param config:       a ``RunConfiguration`` (only ``k_repair_rounds`` is used)
    :param tau:          confidence threshold below which the case escalates
    :param agent_roles:  specialist roles for the multi-agent configuration
    :param repair_rounds: maximum number of planner repair rounds
    :param multi_agent:  build the team; ``False`` builds the single agent
    """
    from langgraph.graph import END, START, StateGraph  # noqa: PLC0415

    from .coordinator import coordinator_node  # noqa: PLC0415
    from .critic import critic_node  # noqa: PLC0415
    from .executor import executor_node  # noqa: PLC0415
    from .planner import planner_node  # noqa: PLC0415
    from .schemas import AgentState  # noqa: PLC0415

    max_repairs = repair_rounds
    if config is not None:
        value = getattr(config, 'k_repair_rounds', None)
        max_repairs = repair_rounds if value is None else int(value)

    graph = StateGraph(AgentState)
    graph.add_node('planner', planner_node(llm))
    graph.add_node('executor', executor_node(config))
    graph.add_edge('executor', END)

    if not multi_agent:
        # One agent plans and acts on its own plan: no coordinator framing
        # the work, no critic reviewing it.
        graph.add_edge(START, 'planner')
        graph.add_edge('planner', 'executor')
        return graph.compile()

    graph.add_node('coordinator', coordinator_node(llm, agent_roles))
    graph.add_node('critic', critic_node(llm, tau=tau, max_repairs=max_repairs))
    graph.add_edge(START, 'coordinator')
    graph.add_edge('coordinator', 'planner')
    graph.add_edge('planner', 'critic')

    def route_after_critic(state: dict) -> str:
        review = (state.get('extras') or {}).get('critic') or {}
        if review.get('goal_reachable', True) or review.get('declined'):
            return 'executor'
        # The critic counts failed critiques; the planner gets ``max_repairs``
        # further attempts after the first one.
        if int(state.get('repair_round', 0)) <= max_repairs:
            return 'planner'
        return 'executor'

    graph.add_conditional_edges(
        'critic',
        route_after_critic,
        {'executor': 'executor', 'planner': 'planner'},
    )

    return graph.compile()

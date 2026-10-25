"""
Executor node.

The executor turns the plan into the executed action sequence.  It is
deliberately *side-effect free* and deterministic: CARMA executes against a
benchmark trace, so the executor records the actions it would perform and
their cost instead of mutating an external system.

The sequence is the plan's activities in plan order.  The executor cannot run
anything the planner — and, in a configuration that has one, the verifier —
did not approve, and it does not grade its own work: whether the case
succeeded is scored against the reference by :mod:`carma_engine.scoring`.

Whether the plan runs at all is decided by the runner after verification.
That is where the least-privilege rule lives: with the SCV on, a plan runs
only with a valid SCV token, which is issued after the graph has finished.
"""
from __future__ import annotations

import logging

log = logging.getLogger('carma')

WRITE_COST = 1.0
READ_COST = 0.1


def executor_node(config=None):
    """Build the LangGraph executor node."""
    def _run(state: dict) -> dict:
        plan = state.get('plan') or {}
        activities = plan.get('activities') or []

        activity_seq = [a.get('activity_name') for a in activities if a.get('activity_name')]
        exec_cost = sum(WRITE_COST if a.get('is_write') else READ_COST for a in activities)
        writes = [a.get('activity_name') for a in activities if a.get('is_write')]

        state['extras'] = {**(state.get('extras') or {}),
                           'executor': {'activity_seq': activity_seq,
                                        'exec_cost': float(exec_cost),
                                        'writes': writes}}
        state['messages'] = list(state.get('messages') or []) + [
            {'role': 'executor',
             'content': f"activity_seq={activity_seq} exec_cost={exec_cost}"}
        ]
        return state

    return _run

"""
Executor node.

The executor turns an approved plan into an executable action sequence.  It is
deliberately *side-effect free*: CARMA executes against a benchmark trace, so
the executor records the actions it would perform and their cost instead of
mutating an external system.  Write actions are only marked executable when a
valid SCV token is present, which is the "least privilege" rule of the paper.
"""
from __future__ import annotations

import logging

log = logging.getLogger('carma')

WRITE_COST = 1.0
READ_COST = 0.1

EXECUTOR_SYSTEM = (
    'You are the executor of a constraint-aware workflow adaptation team. '
    'You receive an approved plan and produce the ordered sequence of actions. '
    'Answer with JSON only.'
)

EXECUTOR_HUMAN = """Plan (JSON):
{plan}

SCV token: {scv_token}

Return JSON:
{{"activity_seq": ["<activity>", "..."],
  "exec_cost": 0.0,
  "task_success": true,
  "notes": "<short execution note>"}}"""


def executor_node(llm, config=None):
    """Build the LangGraph executor node."""
    def _run(state: dict) -> dict:
        plan = state.get('plan') or {}
        activities = plan.get('activities') or []
        scv_token = state.get('scv_token') or ''

        if llm is not None and activities:
            try:
                raw = llm.invoke_json(
                    EXECUTOR_SYSTEM,
                    EXECUTOR_HUMAN.format(plan=plan, scv_token=scv_token or '(none)'),
                    default={},
                ) or {}
                state['llm_calls'] = state.get('llm_calls', 0) + 1
                activity_seq = raw.get('activity_seq') or []
                exec_cost = raw.get('exec_cost')
                task_success = raw.get('task_success')
            except Exception as exc:
                log.warning('Executor LLM call failed (%s) — using deterministic execution.', exc)
                activity_seq, exec_cost, task_success = [], None, None
        else:
            activity_seq, exec_cost, task_success = [], None, None

        if not activity_seq:
            activity_seq = [a.get('activity_name') for a in activities if a.get('activity_name')]

        if exec_cost is None:
            exec_cost = 0.0
            for activity in activities:
                exec_cost += WRITE_COST if activity.get('is_write') else READ_COST
        if task_success is None:
            task_success = bool(activity_seq)

        # Least privilege: without a valid SCV token no write action may run.
        blocked_writes = [
            a.get('activity_name') for a in activities
            if a.get('is_write') and not scv_token
        ]
        if blocked_writes:
            activity_seq = [a for a in activity_seq if a not in blocked_writes]
            task_success = False

        state['extras'] = {**(state.get('extras') or {}),
                           'executor': {'activity_seq': activity_seq,
                                        'exec_cost': float(exec_cost),
                                        'task_success': bool(task_success),
                                        'blocked_writes': blocked_writes}}
        state['messages'] = list(state.get('messages') or []) + [
            {'role': 'executor',
             'content': f"activity_seq={activity_seq} exec_cost={exec_cost}"}
        ]
        return state

    return _run

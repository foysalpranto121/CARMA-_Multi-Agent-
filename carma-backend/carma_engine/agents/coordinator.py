"""
Coordinator node.

Responsibilities
  * normalise the case into a shared working context
  * (multi-agent) elicit one intent per specialist role and detect
    cross-role intent conflicts before any planning happens
  * enforce the hard turn budget (the plan: <= 10 nodes, 30 s) so a
    pathological model cannot loop the graph forever
"""
from __future__ import annotations

import logging

from ..llm.client import LLMUnavailable

log = logging.getLogger('carma')

MAX_AGENT_ROUNDS = 3

COORDINATOR_SYSTEM = (
    'You are the coordinator of a constraint-aware workflow adaptation team. '
    'You do not decide the adaptation yourself; you frame the work, split it '
    'between specialist agents and flag contradictions between their intents. '
    'Answer with JSON only.'
)

COORDINATOR_HUMAN = """Case perturbation (JSON):
{perturbation}

Current process state (JSON):
{process_state}

Prefix trace (JSON):
{prefix_trace}

{roles_block}

Return JSON:
{{"summary": "<one sentence>",
  "intents": [{{"agent": "<role>", "intent": "<what this agent must do>"}}],
  "conflicts": [{{"between": ["<role>", "<role>"], "issue": "<description>"}}],
  "key_risk": "<single most important risk>"}}"""


def coordinator_node(llm, agent_roles: list[str] | None = None):
    """Build the LangGraph coordinator node."""
    agent_roles = agent_roles or []

    def _run(state: dict) -> dict:
        if (state.get('extras') or {}).get('coordinator') is not None:
            # An SCV repair round of the same case: its perturbation, state
            # and prefix are unchanged, so the first round's framing stands.
            return state
        process_state = state.get('process_state') or {}
        roles_block = (
            'Specialist agents available: ' + ', '.join(agent_roles) + '.'
            'Produce one intent per agent.'
            if agent_roles else
            'Single-agent mode: produce a single intent that covers planning, '
            'verification and execution.'
        )
        payload = {
            'perturbation': state.get('perturbation') or {},
            'process_state': process_state,
            'prefix_trace': state.get('prefix_trace') or [],
            'roles_block': roles_block,
        }

        intents: list[dict] = []
        conflicts: list[dict] = []
        summary = ''
        if llm is not None:
            try:
                raw = llm.invoke_json(
                    COORDINATOR_SYSTEM,
                    COORDINATOR_HUMAN.format(**payload),
                    default={},
                )
                intents = raw.get('intents') or []
                conflicts = raw.get('conflicts') or []
                summary = raw.get('summary', '')
                state['llm_calls'] = state.get('llm_calls', 0) + 1
            except LLMUnavailable:
                raise
            except Exception as exc:
                log.warning('Coordinator LLM call failed (%s) — using heuristic framing.', exc)
        else:
            intents = [{'agent': role, 'intent': 'contribute to the adaptation plan'}
                       for role in agent_roles]
            summary = 'Heuristic framing (no LLM available).'

        state['agent_intents'] = intents
        state['extras'] = {**(state.get('extras') or {}),
                           'coordinator': {'summary': summary, 'conflicts': conflicts}}
        state['messages'] = list(state.get('messages') or []) + [
            {'role': 'coordinator', 'content': summary or 'coordinator framing ready'}
        ]
        return state

    return _run

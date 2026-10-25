"""
Critic node.

The critic is the agent-side half of the SCV: it reviews the proposed plan
*before* it is symbolically verified, checks that the plan stays inside the
current stage, that it is backed by evidence, and that the claimed confidence
is defensible.  It can send the plan back to the planner (repair round) when
the goal is not reachable, and it can flag the case for escalation.

A plan in which the planner deliberately declined to act (an empty activity
list from the model) is final: no repair round can turn a refusal to guess
into a plan, so the critic flags the case instead of spending the budget.
"""
from __future__ import annotations

import logging

from ..llm.client import LLMUnavailable

log = logging.getLogger('carma')

CRITIC_SYSTEM = (
    'You are the critic of a constraint-aware workflow adaptation team. '
    'You review a proposed plan against the current process state and the '
    'evidence it cites. Answer with JSON only.'
)

CRITIC_HUMAN = """Plan (JSON):
{plan}

Current stage: {stage}
Enabled activities: {enabled}
Required activities: {required}
Forbidden activities: {forbidden}

Evidence (JSON):
{evidence}

Return JSON:
{{"approved": true,
  "goal_reachable": true,
  "confidence": 0.0,
  "issues": ["<issue>"],
  "suggested_fix": "<what the planner should change>"}}"""


def critic_node(llm, tau: float = 0.5, max_repairs: int = 3):
    """
    Build the LangGraph critic node.

    :param max_repairs: repair rounds the planner gets; once a further
                        critique fails the case is flagged for escalation
    """
    def _run(state: dict) -> dict:
        plan = state.get('plan') or {}
        process_state = state.get('process_state') or {}
        enabled = process_state.get('enabled_activities') or []
        required = process_state.get('required_activities') or []
        forbidden = process_state.get('forbidden_activities') or []
        evidence = state.get('evidence') or []

        if plan.get('plan_source') == 'llm' and not plan.get('activities'):
            state['escalate'] = True
            state['escalation_reason'] = (
                (state.get('escalation_reason') or '') + ' Planner declined to act.').strip()
            state['extras'] = {**(state.get('extras') or {}), 'critic': {
                'approved': False, 'goal_reachable': False, 'declined': True,
                'confidence': plan.get('confidence', 0.0),
                'issues': [f"Planner declined: {plan.get('rationale', '')}".strip()],
                'suggested_fix': '',
            }}
            state['messages'] = list(state.get('messages') or []) + [
                {'role': 'critic', 'content': 'planner declined to act'}]
            return state

        review = {
            'approved': True,
            'goal_reachable': bool(plan.get('goal_reachable', True)),
            'confidence': plan.get('confidence', 0.0),
            'issues': [],
            'suggested_fix': '',
        }

        if llm is not None:
            try:
                review = llm.invoke_json(
                    CRITIC_SYSTEM,
                    CRITIC_HUMAN.format(
                        plan=plan,
                        stage=process_state.get('stage'),
                        enabled=enabled,
                        required=required,
                        forbidden=forbidden,
                        evidence=[{'provenance_id': e.get('provenance_id'),
                                   'title': (e.get('payload') or {}).get('title')}
                                  for e in evidence],
                    ),
                    default=review,
                ) or review
                state['llm_calls'] = state.get('llm_calls', 0) + 1
            except LLMUnavailable:
                raise
            except Exception as exc:
                log.warning('Critic LLM call failed (%s) — mechanical review only.', exc)

        # ── mechanical checks (always applied) ──
        activities = plan.get('activities') or []
        if not activities:
            review['goal_reachable'] = False
            review['issues'] = list(review.get('issues') or []) + ['Plan contains no activities.']
        # An activity is in scope when the model allows it now or when the
        # frame still owes it.  An activity the frame forbids is out of
        # scope whatever else is true.
        in_scope = set(enabled) | set(required)
        off_stage = [a.get('activity_name') for a in activities
                     if a.get('activity_name') not in in_scope]
        if off_stage:
            review['issues'] = list(review.get('issues') or []) + [
                f'Activities not enabled in the current stage: {off_stage}'
            ]
        forbidden_used = [a.get('activity_name') for a in activities
                          if a.get('activity_name') in set(forbidden)]
        if forbidden_used:
            review['issues'] = list(review.get('issues') or []) + [
                f'Activities the frame forbids: {forbidden_used}'
            ]
        missing = [name for name in required
                   if name not in {a.get('activity_name') for a in activities}]
        if missing:
            review['issues'] = list(review.get('issues') or []) + [
                f'Obligations the plan does not discharge: {missing}'
            ]
        if not plan.get('evidence_ids'):
            review['issues'] = list(review.get('issues') or []) + [
                'Plan cites no evidence.'
            ]
            review['confidence'] = min(float(review.get('confidence') or 0.0), 0.4)

        try:
            review['confidence'] = max(0.0, min(1.0, float(review.get('confidence', 0.0))))
        except (TypeError, ValueError):
            review['confidence'] = 0.0

        if not review.get('goal_reachable', True):
            # A failed critique consumes one repair round.
            state['repair_round'] = int(state.get('repair_round', 0)) + 1
            if state['repair_round'] > max_repairs:
                state['escalate'] = True
                state['escalation_reason'] = (
                    (state.get('escalation_reason') or '') + ' Repair budget exhausted.').strip()

        state['extras'] = {**(state.get('extras') or {}), 'critic': review}
        state['messages'] = list(state.get('messages') or []) + [
            {'role': 'critic',
             'content': f"approved={review.get('approved')} "
                        f"goal_reachable={review.get('goal_reachable')} "
                        f"confidence={review.get('confidence')}"}
        ]
        return state

    return _run

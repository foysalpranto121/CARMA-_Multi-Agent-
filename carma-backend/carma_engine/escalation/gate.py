"""
Escalation gate.

A case escalates to a human reviewer when

  * the planner's confidence is below the threshold tau, or
  * the symbolic verifier found a hard constraint violation, or
  * the repair loop exhausted its budget, or
  * the plan itself is not goal-reachable.

``tau`` is a pre-registered hyper-parameter (0.5 by default) and must not be
tuned on the evaluation split.
"""
from __future__ import annotations

TAU_DEFAULT = 0.5


def should_escalate(plan: dict, verdict=None, constraint_graph=None,
                    tau: float = TAU_DEFAULT, repair_rounds: int = 0,
                    max_repair_rounds: int = 3, escalate_flag: bool = False) -> tuple[bool, str]:
    """
    Decide whether a case must be escalated.

    :returns: ``(escalate, reason)``
    """
    plan = plan or {}
    confidence = plan.get('confidence')
    if confidence is None:
        confidence = 1.0
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    if confidence < tau:
        return True, f'Planner confidence {confidence:.2f} below tau={tau}.'

    if escalate_flag:
        return True, 'Escalation requested by the agent graph.'

    report = {}
    if verdict is not None:
        report = getattr(verdict, 'violation_report', None) or (
            verdict.get('violation_report') if isinstance(verdict, dict) else None) or {}
    violations = report.get('violations') or []
    hard = [v for v in violations if v.get('severity') == 'hard']
    if hard:
        names = ', '.join(str(v.get('constraint_id')) for v in hard[:3])
        return True, f'Hard constraint violation(s): {names}.'

    if repair_rounds >= max_repair_rounds and max_repair_rounds > 0:
        return True, 'Repair budget exhausted.'

    if not plan.get('goal_reachable', True):
        return True, 'Plan is not goal-reachable.'

    return False, ''

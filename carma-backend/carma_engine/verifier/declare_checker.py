"""
Declare constraint checker.

Evaluates the declarative templates of the constraint graph against the
projected trace.  The template set implemented here is exactly the set
supported by the process frame model:

    response           if a occurs, b must eventually follow
    precedence         b may only occur if a occurred before
    succession         a and b must alternate (a<b<b>a)
    not_coexistence    a and b must not both occur
    existence          a must occur at least once
    absence            a must not occur
    exactly            a must occur exactly n times
    init               a must be the first activity
"""
from __future__ import annotations

import logging

log = logging.getLogger('carma')


def _violation(constraint_id: str, step: int, severity: str, cost: float, detail: str):
    return {
        'constraint_id': constraint_id,
        'constraint_type': 'declare',
        'offending_step': step,
        'severity': severity,
        'violation_cost': float(cost),
        'min_cost_repair': None,
        'detail': detail,
    }


def _activities_of(params: dict, data: dict) -> tuple:
    activities = (params or {}).get('activities') or []
    a = data.get('activity_a') or (activities[0] if len(activities) > 0 else None)
    b = data.get('activity_b') or (activities[1] if len(activities) > 1 else None)
    return a, b


def evaluate_template(template: str, params: dict, activities: list, data: dict | None = None) -> bool:
    """
    Evaluate one Declare template.

    :returns: ``True`` when the constraint is satisfied.
    """
    data = data or {}
    a, b = _activities_of(params, data)
    n = (params or {}).get('count', params.get('n'))

    if template == 'response':
        for index, activity in enumerate(activities):
            if activity == a and b not in activities[index + 1:]:
                return False
        return True

    if template == 'precedence':
        for index, activity in enumerate(activities):
            if activity == b and a not in activities[:index]:
                return False
        return True

    if template == 'succession':
        # a < b and b < a
        if a in activities and b in activities:
            if activities.index(a) > activities.index(b):
                return False
            if activities.index(b) > activities.index(a):
                return False
        return True

    if template == 'not_coexistence':
        return not (a in activities and b in activities)

    if template == 'existence':
        return a in activities

    if template == 'absence':
        return a not in activities

    if template == 'exactly':
        if n is None:
            return True
        return activities.count(a) == int(n)

    if template == 'init':
        return bool(activities) and activities[0] == a

    # Unknown templates are not violated (forward compatible).
    return True


def check_declare(projected_trace: list, constraint_graph=None,
                  as_of=None) -> list[dict]:
    """Check every Declare constraint of the graph against the projected trace."""
    violations: list[dict] = []
    if constraint_graph is None:
        return violations

    activities = [e.get('activity', '') for e in (projected_trace or [])]

    # A renamed activity is resolved back to the name the declarative
    # constraints use, so that a drift does not break the frame.
    from carma_engine.constraint_knowledge.graph_builder import (
        canonical_activities,
    )

    activities = canonical_activities(activities, constraint_graph)

    from .policy_checker import in_force

    for node_id, data in constraint_graph.nodes(data=True):
        if data.get('template') not in (
            'response', 'precedence', 'succession', 'not_coexistence',
            'existence', 'absence', 'exactly', 'init',
        ):
            continue
        # A constraint that is not in force at the moment of the plan does
        # not apply to it — that is how a rule version is expressed.
        if not in_force(data.get('parameters') or {}, as_of):
            continue
        template = data['template']
        params = data.get('parameters') or {}
        if evaluate_template(template, params, activities, data):
            continue
        violations.append(_violation(
            node_id, len(activities) - 1, data.get('severity', 'hard'),
            data.get('violation_cost', 1.0),
            f'Declare constraint "{template}" violated.'))
    return violations

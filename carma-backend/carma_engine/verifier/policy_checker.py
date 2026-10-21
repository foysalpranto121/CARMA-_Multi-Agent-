"""
Policy checker.

Evaluates the policy family of the process frame P:

    role_required    the plan's activity must be performed by a given role
    amount_limit     a numeric parameter of the plan must stay below a bound
    temporal_window  an activity must fall inside a validity window

A rule lives in the frame as a *version*: it carries the moment it becomes
valid (``valid_from``) and the moment it stops being valid
(``valid_until``).  Only the version that is in force at the moment of the
plan is evaluated, which is what makes a rule change observable: the frame
keeps the old version next to the new one instead of overwriting it.
"""
from __future__ import annotations

import logging

log = logging.getLogger('carma')

POLICY_TEMPLATES = ('role_required', 'amount_limit', 'temporal_window')


def _violation(constraint_id: str, step: int, severity: str, cost: float, detail: str):
    return {
        'constraint_id': constraint_id,
        'constraint_type': 'policy',
        'offending_step': step,
        'severity': severity,
        'violation_cost': float(cost),
        'min_cost_repair': None,
        'detail': detail,
    }


def in_force(params: dict, as_of) -> bool:
    """
    Whether a rule version applies at the given moment.

    A version without a validity window is always in force.
    """
    start = (params or {}).get('valid_from')
    end = (params or {}).get('valid_until')
    if start is None and end is None:
        return True
    if as_of is None:
        # Without a moment to compare against, the version that has no
        # window is the one that can be established.
        return start is None
    moment = str(as_of)
    if start is not None and moment < str(start):
        return False
    if end is not None and moment > str(end):
        return False
    return True


def check_policy(plan: dict, constraint_graph=None, as_of=None) -> list[dict]:
    """Check the policy constraints of the graph against a plan."""
    violations: list[dict] = []
    if constraint_graph is None:
        return violations

    activities = (plan or {}).get('activities') or []
    parameters = (plan or {}).get('parameters') or {}

    for node_id, data in constraint_graph.nodes(data=True):
        template = data.get('template')
        if template not in POLICY_TEMPLATES:
            continue
        params = data.get('parameters') or {}
        severity = data.get('severity', 'hard')
        cost = data.get('violation_cost', 1.0)

        # A rule version that is not in force at the moment of the plan
        # does not apply to it.
        if not in_force(params, as_of):
            continue

        if template == 'role_required':
            required_role = params.get('role') or data.get('activity_b')
            target = data.get('activity_a') or params.get('activity')
            for index, activity in enumerate(activities):
                if target and activity.get('activity_name') != target:
                    continue
                if required_role and activity.get('role') != required_role:
                    violations.append(_violation(
                        node_id, index, severity, cost,
                        f'Activity "{activity.get("activity_name")}" performed by role '
                        f'"{activity.get("role")}" but "{required_role}" is required.'))

        elif template == 'amount_limit':
            field = params.get('field')
            limit = params.get('limit', params.get('max'))
            if field is None or limit is None:
                continue
            value = parameters.get(field)
            if value is None:
                for activity in activities:
                    value = (activity.get('data_payload') or {}).get(field)
                    if value is not None:
                        break
            if value is None:
                continue
            try:
                if float(value) > float(limit):
                    violations.append(_violation(
                        node_id, -1, severity, cost,
                        f'Parameter "{field}"={value} exceeds the limit {limit}.'))
            except (TypeError, ValueError):
                continue

        elif template == 'temporal_window':
            target = data.get('activity_a') or params.get('activity')
            start = params.get('valid_from')
            end = params.get('valid_until')
            if not target or (start is None and end is None):
                continue
            for index, activity in enumerate(activities):
                if activity.get('activity_name') != target:
                    continue
                guard = activity.get('temporal_guard') or {}
                timestamp = guard.get('timestamp') if isinstance(guard, dict) else None
                if timestamp is None:
                    continue
                if start is not None and str(timestamp) < str(start):
                    violations.append(_violation(
                        node_id, index, severity, cost,
                        f'Activity "{target}" executed before its validity window.'))
                if end is not None and str(timestamp) > str(end):
                    violations.append(_violation(
                        node_id, index, severity, cost,
                        f'Activity "{target}" executed after its validity window.'))

    return violations

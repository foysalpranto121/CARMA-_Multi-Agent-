"""
Cross-agent conflict detector.

In the multi-agent configuration several specialists contribute intents.  When
two intents target the same activity with incompatible instructions (e.g. one
approves and the other rejects), the plan is not executable and must be
repaired or escalated.  This is the "conflicting intents" scenario (S5) of
the WF-Adapt benchmark.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger('carma')

# Instruction pairs that cannot both be honoured.
OPPOSING = {
    ('approve', 'reject'),
    ('approve', 'hold'),
    ('escalate', 'approve'),
    ('execute', 'cancel'),
    ('accept', 'refuse'),
}


def _normalise(text: str) -> str:
    return (text or '').strip().lower()


def _mentions(text: str, keyword: str) -> bool:
    """Word-boundary match so "approve the loan" matches the keyword "approve"."""
    return re.search(rf'\b{re.escape(keyword)}\b', text) is not None


def _detect_pair_conflict(first: dict, second: dict) -> str | None:
    a = _normalise(first.get('intent'))
    b = _normalise(second.get('intent'))
    if not a or not b:
        return None
    for left, right in OPPOSING:
        if _mentions(a, left) and _mentions(b, right):
            return (f'Agent "{first.get("agent")}" intends to {left} while agent '
                    f'"{second.get("agent")}" intends to {right}.')
        if _mentions(a, right) and _mentions(b, left):
            return (f'Agent "{first.get("agent")}" intends to {right} while agent '
                    f'"{second.get("agent")}" intends to {left}.')
    return None


def detect_conflicts(all_agent_intents: list, constraint_graph=None) -> list[dict]:
    """
    Detect contradictory instructions between agents.

    :returns: a list of violation dicts (empty when the intents are compatible).
    """
    violations: list[dict] = []
    intents = [i for i in (all_agent_intents or []) if isinstance(i, dict)]
    for index, first in enumerate(intents):
        for second in intents[index + 1:]:
            detail = _detect_pair_conflict(first, second)
            if not detail:
                continue
            violations.append({
                'constraint_id': f'agent_conflict_{first.get("agent")}_{second.get("agent")}',
                'constraint_type': 'conflict',
                'offending_step': -1,
                'severity': 'hard',
                'violation_cost': 1.0,
                'min_cost_repair': None,
                'detail': detail,
            })
    return violations

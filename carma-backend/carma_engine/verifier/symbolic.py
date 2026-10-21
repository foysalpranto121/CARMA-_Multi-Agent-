"""
Symbolic Constraint Verifier (SCV).

The SCV is the action-side constraint layer.  It verifies a proposed
adaptation *before* any write action is executed and, on success, issues an
HMAC-signed plan token.  The executor refuses to run write activities without
a valid token, which implements the least-privilege rule of the paper.

Checks performed
  1. control-flow alignment of the projected trace (prefix + plan)
  2. declarative constraints of the process frame
  3. policy constraints (role, amount, temporal window)
  4. cross-agent intent conflicts
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
import uuid

from .alignment_checker import check_alignment
from .conflict_detector import detect_conflicts
from .declare_checker import check_declare
from .policy_checker import check_policy

log = logging.getLogger('carma')

TOKEN_TTL_SECONDS = 3600


def _signing_secret() -> bytes:
    """Resolve the HMAC secret from the Django settings (or the environment)."""
    try:
        from django.conf import settings  # noqa: PLC0415

        secret = getattr(settings, 'SCV_SIGNING_SECRET', None)
        if secret:
            return str(secret).encode('utf-8')
    except Exception:  # pragma: no cover - settings not configured
        pass
    return (os.environ.get('SCV_SIGNING_SECRET')
            or os.environ.get('DJANGO_SECRET_KEY')
            or 'carma-scv-secret').encode('utf-8')


def verify_token(token: str, secret: bytes | None = None) -> bool:
    """Validate the HMAC signature and the age of a plan token."""
    if not token or '.' not in token:
        return False
    payload, _, signature = token.rpartition('.')
    expected = hmac.new(secret or _signing_secret(), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        _, timestamp = payload.rsplit(':', 1)
        issued_at = int(timestamp)
    except (ValueError, TypeError):
        return False
    return (time.time() - issued_at) <= TOKEN_TTL_SECONDS


class SCVVerifier:
    """
    Verifies plans against a constraint set.

    :param constraint_set: a ``processes.ConstraintSet`` (or ``None`` for an
                           unconstrained verifier, used by the B0 baseline)
    """

    def __init__(self, constraint_set=None, secret: bytes | None = None):
        self.constraint_set = constraint_set
        self.secret = secret or _signing_secret()

    # ── helpers ───────────────────────────────────────────────
    @staticmethod
    def plan_to_trace(plan: dict) -> list[dict]:
        """Project a plan onto a trace of activity steps."""
        return [
            {
                'activity': activity.get('activity_name', ''),
                'role': activity.get('role', ''),
                'data': activity.get('data_payload') or {},
            }
            for activity in (plan or {}).get('activities') or []
        ]

    def issue_token(self, plan: dict) -> str:
        """Issue an HMAC-signed execution token for a plan."""
        plan_id = (plan or {}).get('plan_id') or str(uuid.uuid4())
        payload = f'{plan_id}:{int(time.time())}'
        signature = hmac.new(self.secret, payload.encode('utf-8'), hashlib.sha256).hexdigest()
        return f'{payload}.{signature}'

    # ── main entry point ──────────────────────────────────────
    def verify(self, plan: dict, prefix_trace: list, process=None,
               constraint_graph=None, all_agent_intents: list | None = None):
        """
        Verify a plan.

        :returns: ``(passed, token, total_violation_cost, report)``
        """
        projected = list(prefix_trace or []) + self.plan_to_trace(plan)
        violations: list[dict] = []

        # The moment of the plan is the moment of the case: the last event
        # of the executed prefix.  It decides which version of a rule is
        # in force, and it is a property of the case, not of the agent.
        as_of = _last_timestamp(prefix_trace)

        violations.extend(check_alignment(projected, constraint_graph))
        violations.extend(check_declare(projected, constraint_graph, as_of=as_of))
        violations.extend(check_policy(plan, constraint_graph, as_of=as_of))
        violations.extend(detect_conflicts(all_agent_intents or (plan or {}).get('all_intents') or [],
                                            constraint_graph))

        total_cost = float(sum(v.get('violation_cost', 0.0) for v in violations))
        report = {'violations': violations, 'total_cost': total_cost,
                  'as_of': as_of}

        if violations:
            return False, None, total_cost, report

        return True, self.issue_token(plan), 0.0, report


def _last_timestamp(prefix: list):
    """The moment of the last event of the executed prefix."""
    for event in reversed(prefix or []):
        if isinstance(event, dict):
            timestamp = event.get('timestamp')
            if timestamp:
                return str(timestamp)
    return None

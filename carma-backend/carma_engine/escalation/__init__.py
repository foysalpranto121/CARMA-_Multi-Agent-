"""Escalation gate — decides when a case must be handled by a human."""

from .gate import TAU_DEFAULT, should_escalate

__all__ = ['should_escalate', 'TAU_DEFAULT']

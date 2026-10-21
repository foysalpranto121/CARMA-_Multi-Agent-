"""
Deterministic stand-in for an LLM — a *test double*, not a model.

Purpose
-------
The experiment pipeline (agent graph, escalation gate, verifier loop,
metric aggregation) has to be exercised even when no model endpoint is
reachable.  This module provides a deterministic responder that answers the
planner and critic prompts from the information that the prompt already
carries.

What this is **not**
-------------------
It is not a language model and it produces no model output.  A run that
uses it measures the *plumbing* of the platform, never the quality of an
adaptation.  Every artefact produced through this class is tagged
``llm_backend = "mock"`` so that it can never be mistaken for a model
result, and the experiment command refuses to store such a run under a
configuration whose description claims a model.

Usage
-----
    python manage.py run_experiment --configs B1 --mock-llm
"""
from __future__ import annotations

import json
import logging
import re
import uuid

from .client import Usage

log = logging.getLogger('carma')

#: Marker stored with every run that used this responder.
BACKEND_NAME = 'mock'


def _extract_section(text: str, label: str) -> list[str]:
    """Read a comma-separated list from a labelled line of the prompt."""
    match = re.search(rf'^{re.escape(label)}:\s*(.*)$', text or '', re.MULTILINE)
    if not match:
        return []
    raw = match.group(1).strip()
    if not raw or raw in ('[]', 'none', 'None'):
        return []
    return [item.strip().strip('"\'') for item in raw.split(',') if item.strip()]


class MockLLM:
    """
    Deterministic responder used to validate the pipeline.

    The responder answers the planner prompt with the activities the prompt
    itself lists, so the run exercises exactly the same code path as a
    model call: the same JSON parsing, the same sanitisation, the same
    repair loop, the same verification.
    """

    model = 'mock-deterministic'
    provider = 'mock'

    def __init__(self, seed: int | None = None):
        self.seed = seed
        self.usage = Usage()

    # ── LLMClient-compatible surface ──────────────────────────
    def available(self) -> bool:
        return True

    def invoke(self, system_prompt: str, human_prompt: str) -> str:
        self.usage.calls += 1
        self.usage.prompt_tokens += max(1, len(system_prompt + human_prompt) // 4)

        if 'plan' in (system_prompt or '').lower():
            payload = self._plan(human_prompt)
        elif 'critic' in (system_prompt or '').lower():
            payload = self._critic(human_prompt)
        else:
            payload = {'verdict': 'approve', 'confidence': 0.8,
                       'reasoning': 'mock verdict'}
        text = json.dumps(payload)
        self.usage.completion_tokens += max(1, len(text) // 4)
        return text

    def invoke_json(self, system_prompt: str, human_prompt: str,
                    default: dict | None = None) -> dict:
        from .client import parse_json_object

        raw = self.invoke(system_prompt, human_prompt)
        return parse_json_object(raw, default if default is not None else {})

    # ── the two prompt shapes the agent graph uses ─────────────
    def _plan(self, human_prompt: str) -> dict:
        required = _extract_section(human_prompt, 'Required activities')
        enabled = _extract_section(human_prompt, 'Enabled activities')
        forbidden = set(_extract_section(human_prompt, 'Forbidden activities'))

        # The role of an activity is knowledge, not state: it comes from the
        # retrieved evidence.  The mock reads it from the evidence pack it
        # was given, exactly as a model would.
        roles: dict[str, str] = {}
        for match in re.finditer(
                r'Activity "([^"]+)" is performed in the role "([^"]+)"',
                human_prompt or ''):
            roles.setdefault(match.group(1), match.group(2))

        activities = []
        for name in required + enabled:
            if name in forbidden or name in [a['activity_name'] for a in activities]:
                continue
            activities.append({
                'activity_name': name,
                'role': roles.get(name, 'system'),
                'data_payload': {},
                'is_write': False,
            })
        evidence = re.findall(r'PRV-[0-9A-F]{8}', human_prompt or '')
        return {
            'plan_id': str(uuid.uuid4()),
            'activities': activities,
            'parameters': {},
            'evidence_ids': evidence[:3],
            'confidence': 0.7 if activities else 0.2,
            'rationale': 'Deterministic mock plan built from the prompt state.',
            'goal_reachable': bool(activities),
        }

    def _critic(self, human_prompt: str) -> dict:
        return {
            'verdict': 'approve',
            'confidence': 0.75,
            'reasoning': 'Deterministic mock verdict: no violation detected.',
        }

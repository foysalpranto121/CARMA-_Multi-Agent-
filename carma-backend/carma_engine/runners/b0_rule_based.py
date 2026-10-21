"""
B0 — Rule-Based baseline.

No LLM, no retrieval.  The adaptation is produced by a deterministic planner
that walks the ordering constraints of the process frame and proposes the
currently enabled activities in a constraint-respecting order.

This is the control condition of the factorial design: it must not use CAR
(no retrieval) and must not use the SCV (the pre-execution symbolic verifier
is off), so any measured difference against B4-B7 is attributable to the
component under test.
"""
from __future__ import annotations

import logging
import uuid

import networkx as nx

from .base import BaseRunner

log = logging.getLogger('carma')

# Confidence assigned to the deterministic planner.  It is a property of the
# rule engine (it either finds a valid ordering or it does not), not a
# free parameter, and it is identical across all cases.
CONFIDENCE_WITH_PLAN = 0.8
CONFIDENCE_WITHOUT_PLAN = 0.2


class B0RuleBasedRunner(BaseRunner):
    code = 'B0'
    retrieval_type = 'none'
    multi_agent = False
    use_scv = False
    num_agents = 0

    def plan_case(self, benchmark_case, state, constraint_graph, evidence):
        # The rule engine follows the process frame: it discharges the
        # obligations the executed prefix left open, in the order the frame
        # imposes, and adds the activities the model enables now.  It has no
        # retrieval and no verification loop, so the frame is all it can
        # offer.
        enabled = list(state.enabled_activities or [])
        required = [name for name in (state.required_activities or [])
                    if name not in (state.forbidden_activities or [])]
        forbidden = set(state.forbidden_activities or [])
        done = {event.get('activity')
                for event in (getattr(benchmark_case, 'prefix_trace', None) or [])
                if event.get('activity')}
        # An activity the prefix already executed is done, unless the frame
        # asks for it again: a response obligation outlives the occurrence
        # that raised it, and a case that loops has to loop.
        candidates = [name for name in required + enabled
                      if name not in forbidden
                      and (name in required or name not in done)]
        ordered = self._ordered_activities(constraint_graph, candidates)

        roles = self._frame_roles(constraint_graph)
        activities = [
            {
                'activity_name': name,
                'role': roles.get(name, 'system'),
                'data_payload': {},
                'is_write': False,
            }
            for name in ordered
        ]
        goal_reachable = bool(activities)
        confidence = CONFIDENCE_WITH_PLAN if goal_reachable else CONFIDENCE_WITHOUT_PLAN

        plan = {
            'plan_id': str(uuid.uuid4()),
            'activities': activities,
            'parameters': {},
            'evidence_ids': [],
            'confidence': confidence,
            'rationale': 'Rule-based ordering of the currently enabled activities.',
            'goal_reachable': goal_reachable,
        }
        return {
            'plan': plan,
            'plan_id': plan['plan_id'],
            'activity_seq': ordered,
            'confidence': confidence,
            'exec_cost': 0.1 * len(ordered),
            'task_success': goal_reachable,
            'repair_rounds': 0,
            'escalate': not goal_reachable,
            'escalation_reason': '' if goal_reachable else 'No enabled activity available.',
            'llm_calls': 0,
            'agent_intents': [],
        }

    @staticmethod
    def _frame_roles(constraint_graph) -> dict:
        """
        The role the process frame demands for each activity.

        The frame is the process definition, not retrieved knowledge, so the
        rule-based engine may read it: a rule engine that had to guess who
        performs an activity would be measuring the role constraints rather
        than the component under test.
        """
        roles: dict[str, str] = {}
        if constraint_graph is None:
            return roles
        for _, data in constraint_graph.nodes(data=True):
            if data.get('template') != 'role_required':
                continue
            activity = data.get('activity_a')
            role = (data.get('parameters') or {}).get('role') or data.get('activity_b')
            if activity and role:
                roles[activity] = role
        return roles

    @staticmethod
    def _ordered_activities(constraint_graph, enabled: list[str]) -> list[str]:
        """
        Order the enabled activities so that the binary ordering constraints
        (response / precedence / succession) are respected.
        """
        if not enabled:
            return []
        if constraint_graph is None:
            return list(enabled)

        subgraph = constraint_graph.subgraph([a for a in enabled if a in constraint_graph])
        try:
            order = list(nx.topological_sort(subgraph))
        except (nx.NetworkXUnfeasible, nx.NetworkXError):
            order = []
        ordered = [a for a in order if a in enabled]
        ordered += [a for a in enabled if a not in ordered]
        return ordered

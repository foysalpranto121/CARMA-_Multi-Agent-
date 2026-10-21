"""
Control-flow alignment checker.

The verifier checks that the projected trace (the executed prefix plus the
planned activities) still follows the procedural model.  When PM4Py is
available the real alignment is computed; otherwise a cheaper syntactic
check is used: every planned activity must be a declared activity of the
process.

A benchmark case carries a *prefix* of a process, so the trace never reaches
the final marking of the model.  The checker therefore charges only the
deviations of the trace — the activities the model cannot explain and the
modelled activities the trace skipped — and not the part of the process
that has simply not been executed yet.
"""
from __future__ import annotations

import logging

log = logging.getLogger('carma')


def _violation(constraint_id: str, constraint_type: str, step: int,
               severity: str, cost: float, detail: str = ''):
    return {
        'constraint_id': constraint_id,
        'constraint_type': constraint_type,
        'offending_step': step,
        'severity': severity,
        'violation_cost': float(cost),
        'min_cost_repair': None,
        'detail': detail,
    }


def check_alignment(projected_trace: list, constraint_graph=None) -> list[dict]:
    """
    Check the control-flow alignment of a projected trace.

    :returns: a list of violation dicts (empty when the trace aligns).
    """
    violations: list[dict] = []
    activities = [e.get('activity', '') for e in (projected_trace or [])]

    # A renamed activity is resolved back to the name the model uses, so
    # that the frame judges the behaviour and not the spelling.
    canonical = activities
    if constraint_graph is not None:
        from carma_engine.constraint_knowledge.graph_builder import (
            canonical_activities,
        )

        canonical = canonical_activities(activities, constraint_graph)

    model_xml = (constraint_graph.graph.get('model_xml', '') if constraint_graph is not None else '')
    if model_xml:
        try:
            from carma_engine.pm4py_compat import alignment_detail_for_model

            detail = alignment_detail_for_model(model_xml, canonical)
            if detail.get('inconclusive'):
                # The exact alignment search ran out of time on this
                # trace.  Rather than reporting a violation that was
                # never established, the syntactic check below decides.
                log.info('Alignment search inconclusive for %d activities — '
                         'using the syntactic check.', len(activities))
            else:
                cost = float(detail.get('cost', 0.0))
                if cost > 0:
                    violations.append(_violation(
                        'control_flow_alignment', 'alignment',
                        len(activities) - 1, 'hard', cost,
                        f'{cost:g} control-flow deviation(s): '
                        f'{detail["log_moves"]} unexplainable activity/activities, '
                        f'{detail["model_moves"]} modelled activity/activities '
                        f'skipped by the trace.'))
                return violations
        except Exception as exc:
            log.info('PM4Py alignment unavailable (%s) — using syntactic check.', exc)

    # Fallback: the planned activities must exist in the process frame.
    declared = set()
    if constraint_graph is not None:
        declared = {a for a in (constraint_graph.graph.get('activities') or []) if a}
    if not declared:
        return violations
    for index, activity in enumerate(canonical):
        if activity and activity not in declared:
            violations.append(_violation(
                'control_flow_alignment', 'alignment', index, 'hard', 1.0,
                f'Activity "{activities[index]}" is not declared by the '
                f'process frame.'))
    return violations

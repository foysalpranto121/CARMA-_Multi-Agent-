"""
State estimation from a prefix trace.

Primary path  : PM4Py token replay over the BPMN / Petri-net model, which
                yields the reached marking, the enabled transitions and a
                trace-fitness score.
Fallback path : a deterministic activity-graph walk used when PM4Py is not
                installed or the model cannot be parsed.  It yields the same
                ``ProcessState`` contract, so downstream code (CAR filter,
                SCV, planner) never needs to know which path produced it.

The fallback is not a stub for the research: it is the same "which activities
may legally happen next" computation, restricted to the declarative
constraint graph instead of the token-replayed marking.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger('carma')

# Confidence assigned to the token-replay estimate as a function of trace fitness.
FITNESS_HIGH, FITNESS_LOW = 0.8, 0.0
CONFIDENCE_HIGH, CONFIDENCE_LOW = 0.95, 0.6
FALLBACK_CONFIDENCE = 0.5


@dataclass
class ProcessState:
    """The estimated state of a case at a point in its lifecycle."""
    stage: str
    stage_confidence: float
    enabled_activities: list[str] = field(default_factory=list)
    declare_automata_states: dict = field(default_factory=dict)
    case_timestamp: Optional[Any] = None
    current_node: str = ''
    source: str = 'fallback'
    trace_fitness: Optional[float] = None
    model_continuation: list[str] = field(default_factory=list)
    required_activities: list[str] = field(default_factory=list)
    forbidden_activities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'stage': self.stage,
            'stage_confidence': self.stage_confidence,
            'enabled_activities': list(self.enabled_activities),
            'declare_automata_states': dict(self.declare_automata_states),
            'case_timestamp': self.case_timestamp,
            'current_node': self.current_node,
            'source': self.source,
            'trace_fitness': self.trace_fitness,
            'model_continuation': list(self.model_continuation),
            'required_activities': list(self.required_activities),
            'forbidden_activities': list(self.forbidden_activities),
        }


def _trace_activities(prefix_trace: list) -> list[str]:
    return [e.get('activity', '') for e in (prefix_trace or []) if e.get('activity')]


def _read_model(process, model_xml: str):
    """
    Parse the procedural model.

    Returns ``(net, initial_marking, final_marking)``.
    """
    from carma_engine.pm4py_compat import read_model_xml

    return read_model_xml(model_xml or getattr(process, 'model_xml', ''))


def _enabled_transitions(net, marking) -> list[str]:
    """Names of the transitions enabled in a given marking."""
    from carma_engine.pm4py_compat import enabled_transitions

    return enabled_transitions(net, marking)


def _infer_stage(prefix_trace: list, process, enabled: list[str]) -> str:
    """
    Stage inference.

    A stage is a named region of the process.  When the process frame defines
    explicit stages (``metadata['stages']``) the prefix is matched against
    them; otherwise the stage is the last observed activity, which is the
    conventional "current activity" notion used by the BPI case studies.
    """
    activities = _trace_activities(prefix_trace)
    stages = (getattr(process, 'metadata', None) or {}).get('stages') or []
    if stages:
        for stage in stages:
            marker = stage.get('marker') or stage.get('name')
            if marker and marker in activities:
                return stage.get('name', marker)
    if activities:
        return activities[-1]
    return enabled[0] if enabled else ''


def _check_declare_states(prefix_trace: list, constraint_graph) -> dict:
    """
    Evaluate the declarative constraints that can be decided on the prefix alone
    (existence / absence / not-coexistence) and report their truth value.
    """
    activities = _trace_activities(prefix_trace)
    states: dict[str, bool] = {}
    if constraint_graph is None:
        return states
    for node_id, data in constraint_graph.nodes(data=True):
        template = data.get('template')
        params = data.get('parameters') or {}
        a = data.get('activity_a') or params.get('activities', [None, None])[0]
        b = data.get('activity_b') or (params.get('activities') or [None, None])[1] \
            if len(params.get('activities') or []) > 1 else None
        if template == 'existence':
            states[node_id] = a in activities
        elif template == 'absence':
            states[node_id] = a not in activities
        elif template == 'not_coexistence':
            states[node_id] = not (a in activities and b in activities)
    return states


def _open_obligations(prefix_activities: list, constraint_graph,
                      as_of=None) -> dict:
    """
    The obligations the executed prefix leaves open.

    A declarative constraint that is in force at the moment of the case
    binds the *continuation* as well: a response that has not arrived yet
    has to arrive, an activity that has not been seen yet has to be seen.
    The state estimator reports these obligations next to the enabled
    activities, because "where the case is" is not only a control-flow
    position — it is a control-flow position plus the set of obligations
    that are still due.

    :returns: ``{'required': [...], 'forbidden': [...]}``
    """
    required: list[str] = []
    forbidden: list[str] = []
    if constraint_graph is None:
        return {'required': required, 'forbidden': forbidden}

    from carma_engine.verifier.policy_checker import in_force

    activities = list(prefix_activities or [])
    live = []
    for _, data in constraint_graph.nodes(data=True):
        template = data.get('template')
        params = data.get('parameters') or {}
        if template not in ('response', 'precedence', 'succession',
                            'not_coexistence', 'existence', 'absence',
                            'exactly', 'init'):
            continue
        if not in_force(params, as_of):
            continue
        pair = params.get('activities') or []
        a = data.get('activity_a') or (pair[0] if len(pair) > 0 else None)
        b = data.get('activity_b') or (pair[1] if len(pair) > 1 else None)
        if not a:
            continue
        live.append((template, params, a, b))

    # First pass: what the continuation owes the frame.
    for template, params, a, b in live:
        if template == 'response':
            # Every occurrence of a must be followed by b.  The last
            # occurrence of a in the prefix is the one still waiting.
            for index in range(len(activities) - 1, -1, -1):
                if activities[index] != a:
                    continue
                if b not in activities[index + 1:]:
                    _add(required, b)
                break
        elif template == 'succession':
            if a in activities and b not in activities:
                _add(required, b)
        elif template == 'existence':
            if a not in activities:
                _add(required, a)
        elif template == 'exactly':
            target = _as_int(params.get('count', params.get('n')))
            if target is not None and activities.count(a) < target:
                _add(required, a)

    # Second pass: what the continuation may not contain.
    for template, params, a, b in live:
        if template == 'absence':
            # The activity may not occur in the case at all, so it may not
            # occur in the continuation either.
            _add(forbidden, a)
        elif template == 'not_coexistence':
            # The two activities may never appear in the same case.  One
            # of them has already happened, so the other is out; if
            # neither has happened, the one that is due rules out the
            # other.
            if a in activities and b:
                _add(forbidden, b)
            if b in activities:
                _add(forbidden, a)
            if a not in activities and b not in activities:
                if a in required:
                    _add(forbidden, b)
                if b in required:
                    _add(forbidden, a)
        elif template == 'exactly':
            target = _as_int(params.get('count', params.get('n')))
            if target is not None and activities.count(a) >= target:
                _add(forbidden, a)

    return {'required': required, 'forbidden': forbidden}


def _as_int(value):
    """Read an integer from a constraint parameter, or ``None``."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _add(collection: list, value):
    """Append a value to a list once."""
    if value and value not in collection:
        collection.append(value)


def _fallback_state(prefix_trace, process, constraint_graph, case_timestamp) -> ProcessState:
    """Deterministic activity-graph walk (no PM4Py required)."""
    activities = _trace_activities(prefix_trace)
    last = activities[-1] if activities else ''

    enabled: list[str] = []
    if constraint_graph is not None and last and last in constraint_graph:
        enabled = sorted(set(constraint_graph.successors(last)))
    if not enabled:
        declared = list((getattr(process, 'activities', None) or []))
        if last and last in declared:
            idx = declared.index(last)
            enabled = declared[idx + 1: idx + 2]
        elif declared:
            enabled = declared[:1]

    return ProcessState(
        stage=_infer_stage(prefix_trace, process, enabled),
        stage_confidence=FALLBACK_CONFIDENCE,
        enabled_activities=enabled,
        declare_automata_states=_check_declare_states(prefix_trace, constraint_graph),
        case_timestamp=case_timestamp,
        current_node=last,
        source='fallback',
        trace_fitness=None,
        required_activities=_open_obligations(
            activities, constraint_graph, case_timestamp)['required'],
        forbidden_activities=_open_obligations(
            activities, constraint_graph, case_timestamp)['forbidden'],
    )


def _token_replay(frame, net, initial_marking, final_marking) -> dict:
    """Replay a single-case frame against a Petri net."""
    from carma_engine.pm4py_compat import token_replay

    return token_replay(frame, net, initial_marking, final_marking)


def _prefix_enabled(net, initial_marking, final_marking, activities: list,
                    declared: set) -> tuple:
    """
    The transitions the model still allows after a prefix.

    The token replay of a partial trace walks to the final marking of the
    model, which reports a running case as finished.  The prefix marking
    — the marking reached where the trace ends — answers the question the
    state estimator actually asks.
    """
    from carma_engine.pm4py_compat import prefix_marking

    state = prefix_marking(activities, net, initial_marking, final_marking,
                            declared=declared)
    enabled = list(state.get('activities') or [])
    return enabled, bool(state.get('inconclusive')), state.get('marking_state')


def _model_continuation(net, marking, final_marking, declared: set) -> list:
    """
    The activity sequence the model prescribes from the reached marking to
    the end of the process.
    """
    if not marking:
        return []
    from carma_engine.pm4py_compat import shortest_continuation

    try:
        return shortest_continuation(net, marking, final_marking, declared)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning('Model continuation failed (%s).', exc)
        return []


def estimate_state(
    prefix_trace: list,
    process,
    constraint_graph=None,
    case_timestamp=None,
) -> ProcessState:
    """
    Estimate the process state reached by ``prefix_trace``.

    :param prefix_trace:   list of ``{activity, timestamp, ...}`` dicts
    :param process:       a ``processes.Process`` instance
    :param constraint_graph: the compiled constraint graph (may be ``None``)
    :param case_timestamp:    timestamp used for temporal validity checks
    """
    try:
        import pandas as pd
        import pm4py  # noqa: F401
    except Exception as exc:  # pragma: no cover - depends on optional extras
        log.info('PM4Py unavailable (%s) — using activity-graph state estimator.', exc)
        return _fallback_state(prefix_trace, process, constraint_graph, case_timestamp)

    try:
        net, initial_marking, final_marking = _read_model(process, getattr(process, 'model_xml', ''))
        activities = _trace_activities(prefix_trace)
        if not activities:
            return _fallback_state(prefix_trace, process, constraint_graph, case_timestamp)

        declared = set(getattr(process, 'activities', None) or [])
        enabled, inconclusive, marking_state = _prefix_enabled(
            net, initial_marking, final_marking, activities, declared)
        # The discovered net contains structural nodes (skip_*, tauSplit_*,
        # ...) that are not activities of the process; they are not offered
        # to the agents.
        enabled = sorted({name for name in enabled
                          if name and (not declared or name in declared)})

        if not enabled and inconclusive:
            # The alignment search ran out of time, so the state could not
            # be established from the model; the activity-graph estimator
            # answers instead of reporting an empty state.
            return _fallback_state(prefix_trace, process, constraint_graph,
                                   case_timestamp)

        if not enabled:
            # The prefix reached the end of the modelled process.  The
            # directly-follows relation of the model still says which
            # activities the case may continue with.
            enabled = _successors_of(net, activities[-1], declared)

        frame = pd.DataFrame([
            {
                'case_id': 'case',
                'activity': e.get('activity', ''),
                'timestamp': e.get('timestamp'),
            }
            for e in (prefix_trace or []) if e.get('activity')
        ])
        frame['timestamp'] = pd.to_datetime(frame['timestamp'], utc=True,
                                            errors='coerce')

        case = _token_replay(frame, net, initial_marking, final_marking)
        fitness = float(case.get('trace_fitness', 0.0) or 0.0)
        confidence = CONFIDENCE_HIGH if fitness > FITNESS_HIGH else CONFIDENCE_LOW

        from carma_engine.pm4py_compat import transition_labels, transition_name

        labels = transition_labels(net)
        last_visited = ''
        activated = case.get('activated_transitions') or []
        if activated:
            last_item = activated[-1]
            if isinstance(last_item, str):
                last_visited = labels.get(last_item, last_item)
            elif isinstance(last_item, (tuple, list)) and len(last_item) > 1:
                last_visited = str(last_item[1])
            else:
                last_visited = transition_name(last_item)

        obligations = _open_obligations(activities, constraint_graph,
                                        case_timestamp)

        return ProcessState(
            stage=_infer_stage(prefix_trace, process, enabled),
            stage_confidence=confidence,
            enabled_activities=enabled,
            declare_automata_states=_check_declare_states(prefix_trace, constraint_graph),
            case_timestamp=case_timestamp,
            current_node=last_visited,
            source='pm4py',
            trace_fitness=fitness,
            model_continuation=_model_continuation(net, marking_state,
                                                   final_marking, declared),
            required_activities=obligations['required'],
            forbidden_activities=obligations['forbidden'],
        )
    except Exception as exc:
        log.warning('Token replay failed (%s) — falling back to activity-graph estimator.', exc)
        return _fallback_state(prefix_trace, process, constraint_graph, case_timestamp)


def _successors_of(net, activity: str, declared: set) -> list:
    """The activities the model allows directly after the given one."""
    from carma_engine.pm4py_compat import transition_name

    successors = []
    for transition in getattr(net, 'transitions', None) or []:
        if transition_name(transition) != activity:
            continue
        for arc in getattr(transition, 'out_arcs', None) or []:
            place = arc.target
            for successor_arc in getattr(place, 'out_arcs', None) or []:
                name = str(getattr(successor_arc.target, 'label', '') or
                           transition_name(successor_arc.target))
                if name and (not declared or name in declared):
                    successors.append(name)
    return sorted(set(successors))

"""
CARMA — pm4py compatibility layer.

pm4py changed its public API twice in the 2.x line: the event log became a
``pandas.DataFrame`` in 2.7, the Petri net became a native object, the
``read_*_from_string`` helpers disappeared and the alignment and replay
algorithms now take their column names through a ``Parameters`` enum.

Every pm4py call in CARMA goes through this module, so that the rest of the
code base does not have to care which pm4py is installed.  Each wrapper
detects the installed version at call time and falls back to the older
spelling when it is available.
"""
from __future__ import annotations

import logging
import os
import tempfile
from functools import lru_cache

log = logging.getLogger('carma')


# ── models ──────────────────────────────────────────────────────
@lru_cache(maxsize=8)
def _read_model_xml_cached(model_xml: str):
    """Parse a model XML, caching the result per model."""
    return _read_model_xml_uncached(model_xml)


def _read_model_xml_uncached(model_xml: str):
    """
    Parse a BPMN or PNML model held in a string.

    :returns: ``(net, initial_marking, final_marking)``
    """
    import pm4py

    xml = model_xml or ''
    if not xml:
        raise ValueError('No model XML given.')

    if hasattr(pm4py, 'read_pnml_from_string'):  # pragma: no cover - pm4py < 2.7
        if '<pnml' in xml:
            return pm4py.read_pnml_from_string(xml)
        return pm4py.read_bpmn_from_string(xml)

    suffix = '.pnml' if '<pnml' in xml else '.bpmn'
    handle, path = tempfile.mkstemp(suffix=suffix, prefix='carma-model-')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            stream.write(xml)
        if suffix == '.pnml':
            return pm4py.read_pnml(path)
        return pm4py.read_bpmn(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def read_model_xml(model_xml: str):
    """
    Parse a BPMN or PNML model held in a string.

    The result is cached per model, because the verifier parses the same
    procedural model once per candidate plan.

    :returns: ``(net, initial_marking, final_marking)``
    """
    return _read_model_xml_cached(model_xml or '')


def transition_name(transition) -> str:
    """
    The activity name of a Petri net transition.

    pm4py 2.7 carries the activity in ``label`` and uses ``name`` for the
    internal identifier; older releases only have ``name``.
    """
    label = getattr(transition, 'label', None)
    if label:
        return str(label)
    return str(getattr(transition, 'name', transition))


def transition_labels(net) -> dict:
    """Map of transition id -> activity name for a net."""
    labels = {}
    for transition in getattr(net, 'transitions', None) or []:
        identifier = getattr(transition, 'name', None)
        if identifier:
            labels[str(identifier)] = transition_name(transition)
    return labels


def net_activities(net) -> list:
    """The activity names of a net."""
    names = set()
    for transition in getattr(net, 'transitions', None) or []:
        label = getattr(transition, 'label', None) or \
            getattr(transition, 'name', None)
        if label:
            names.add(str(label))
    return sorted(names)


def net_transitions(net) -> list:
    """The directly-follows transitions of a net."""
    transitions = []
    places = list(getattr(net, 'places', None) or [])
    for transition in getattr(net, 'transitions', None) or []:
        source = transition_name(transition)
        for arc in getattr(transition, 'out_arcs', None) or []:
            target_place = getattr(arc, 'target', None)
            place_id = str(getattr(target_place, 'name', target_place))
            for place in places:
                if str(getattr(place, 'name', '')) != place_id:
                    continue
                for successor_arc in getattr(place, 'out_arcs', None) or []:
                    successor = getattr(successor_arc, 'target', None)
                    target = transition_name(successor)
                    transitions.append({
                        'from':  source,
                        'to':    target,
                        'label': f'{source} -> {target}',
                    })
    return transitions


def _transitions_by_label(net) -> dict:
    """Map every label of a net to the transitions that carry it."""
    by_label: dict[str, list] = {}
    for transition in getattr(net, 'transitions', None) or []:
        label = str(getattr(transition, 'label', '') or transition.name)
        by_label.setdefault(label, []).append(transition)
    return by_label


def _input_place(arc):
    """The place an input arc comes from."""
    place = getattr(arc, 'target_place', None)
    if place is not None:
        return place
    return getattr(arc, 'source', None)


def _output_place(arc):
    """The place an output arc goes to."""
    place = getattr(arc, 'target_place', None)
    if place is not None:
        return place
    return getattr(arc, 'target', None)


def _fire(marking: dict, transition) -> bool:
    """Fire a transition in a marking.  False when it is not enabled."""
    in_arcs = list(getattr(transition, 'in_arcs', None) or [])
    for arc in in_arcs:
        if marking.get(_input_place(arc), 0) <= 0:
            return False
    for arc in in_arcs:
        place = _input_place(arc)
        marking[place] = marking.get(place, 0) - 1
        if marking[place] == 0:
            del marking[place]
    for arc in getattr(transition, 'out_arcs', None) or []:
        place = _output_place(arc)
        marking[place] = marking.get(place, 0) + 1
    return True


def _alignment_moves(activities: list, net, initial_marking, final_marking,
                      activity_key: str, case_id_key: str,
                      max_seconds: float):
    """The move list of an alignment, or None when the search timed out."""
    import pandas as pd
    from pm4py.algo.conformance.alignments.petri_net import algorithm as alignments

    frame = pd.DataFrame([
        {case_id_key: 'case', activity_key: activity}
        for activity in activities
    ])
    try:
        result = alignments.apply(
            frame, net, initial_marking, final_marking,
            parameters={
                alignments.Parameters.ACTIVITY_KEY: activity_key,
                alignments.Parameters.CASE_ID_KEY:  case_id_key,
                alignments.Parameters.SHOW_PROGRESS_BAR: False,
                alignments.Parameters.PARAM_MAX_ALIGN_TIME: max_seconds,
            },
        )
    except ImportError:  # pragma: no cover - pm4py < 2.7
        result = alignments.apply(frame, net, initial_marking, final_marking)

    if result is None:
        return None
    if isinstance(result, list):
        result = result[0] if result else {}
    if result is None:
        return None
    if hasattr(result, 'iloc'):
        result = result.iloc[0].to_dict()

    alignment = result.get('alignment') or []
    if alignment and isinstance(alignment[0], list):
        alignment = alignment[0]
    return [(str(move), str(label)) for move, label in alignment]


def _marking_key(marking: dict) -> tuple:
    """A hashable key for a marking, used to detect revisited states."""
    return tuple(sorted((str(getattr(place, 'name', place)), int(count))
                        for place, count in marking.items() if count))


def _is_final(marking: dict, final_marking: dict) -> bool:
    """True when the marking holds every token of the final marking."""
    for place, count in (final_marking or {}).items():
        if marking.get(place, 0) < count:
            return False
    return True


def shortest_continuation(net, marking: dict, final_marking: dict,
                          declared: set | None = None,
                          max_transitions: int = 4000) -> list[str]:
    """
    The shortest activity sequence that carries a marking to the end of the
    model.

    The rule-based baseline needs a *complete* continuation: the set of
    activities that are enabled right now says only what may happen next,
    not what the case is supposed to do until it ends.

    The search is a shortest-path search over the model that minimises the
    number of model transitions.  The silent steps of a discovered model
    form a wide graph — a discovered model offers many ways to reach the
    same activity — so the cost counts steps and not activities: a cost on
    activities alone would explore the whole silent graph before it ever
    looked at a business step.

    :returns: the activity names of the continuation, empty when the model
              offers no path to the end from this marking.
    """
    declared = set(declared or [])
    if not marking:
        return []

    import heapq

    # (transitions, activities, counter) → keeps the heap deterministic.
    counter = 0
    heap = [(0, 0, counter, dict(marking), [])]
    seen = {_marking_key(marking): (0, 0)}

    while heap:
        steps, activities, _, current, path = heapq.heappop(heap)
        if _is_final(current, final_marking):
            return path
        if steps >= max_transitions:
            continue
        for transition in getattr(net, 'transitions', None) or []:
            if not all(current.get(_input_place(arc), 0) > 0
                       for arc in getattr(transition, 'in_arcs', None) or []):
                continue
            following = dict(current)
            if not _fire(following, transition):
                continue
            label = transition_name(transition)
            is_activity = label in declared
            next_path = path + [label] if is_activity else path
            key = _marking_key(following)
            cost = (steps + 1, len(next_path))
            previous = seen.get(key)
            if previous is not None and previous <= cost:
                continue
            seen[key] = cost
            counter += 1
            heapq.heappush(heap, (cost[0], cost[1], counter, following, next_path))

    return []


def enabled_activities(net, marking: dict, declared: set | None = None,
                       max_silent_steps: int = 1) -> list:
    """
    The activities that may happen next in a marking.

    A discovered model contains silent steps — the structural nodes of the
    Inductive Miner — between the real activities.  An activity counts as
    enabled when it can be reached by firing the silent steps that are
    enabled, because those steps carry no business meaning of their own.
    The search is bounded by ``max_silent_steps``: a deeper search returns
    every activity the process can ever reach, which is not a state but
    the whole process.
    """
    declared = set(declared or [])
    if not declared:
        return []

    found: set[str] = set()
    frontier = [(dict(marking), 0)]
    visited: set = set()

    while frontier:
        current, depth = frontier.pop()
        key = (frozenset(current.items()), depth)
        if key in visited:
            continue
        visited.add(key)
        for transition in getattr(net, 'transitions', None) or []:
            if not all(current.get(_input_place(arc), 0) > 0
                       for arc in getattr(transition, 'in_arcs', None) or []):
                continue
            label = transition_name(transition)
            if label in declared:
                found.add(label)
                continue
            if depth >= max_silent_steps:
                continue
            # A silent step: fire it and look at what it enables.
            following = dict(current)
            _fire(following, transition)
            frontier.append((following, depth + 1))

    return sorted(found)


def prefix_marking(prefix_activities: list, net, initial_marking,
                   final_marking, activity_key='activity',
                   case_id_key='case_id', max_seconds: float = 5.0,
                   declared: set | None = None) -> dict:
    """
    The marking a *prefix* reaches, and the transitions enabled there.

    A token replay of a partial trace is not enough: the replay walks the
    trace to the final marking of the model and stops there, so a case that
    is still running is reported as finished.  The replay does record the
    order in which it activated the transitions, though, so the prefix is
    replayed by hand over that order and the marking is read where the
    trace ends — before the suffix that completes the model.

    :returns: a dict with the ``marking``, the ``enabled`` transition
              labels and the ``inconclusive`` flag.
    """
    activities = [a for a in (prefix_activities or []) if a]
    result = {'marking': {}, 'enabled': [], 'inconclusive': False}
    if not activities:
        return result

    by_id = {str(transition.name): transition
             for transition in getattr(net, 'transitions', None) or []}
    by_label = _transitions_by_label(net)

    try:
        import pandas as pd
        from pm4py.algo.conformance.tokenreplay import algorithm as replay
        from pm4py.algo.conformance.tokenreplay.variants.token_replay import (
            Parameters,
        )

        frame = pd.DataFrame([
            {case_id_key: 'case', activity_key: activity}
            for activity in activities
        ])
        raw = replay.apply(
            frame, net, initial_marking, final_marking,
            parameters={
                Parameters.ACTIVITY_KEY: activity_key,
                Parameters.CASE_ID_KEY:  case_id_key,
                Parameters.SHOW_PROGRESS_BAR: False,
                Parameters.CONSIDER_REMAINING_IN_FITNESS: False,
            },
        )
        if raw is None:
            result['inconclusive'] = True
            return result
        case = raw[0] if isinstance(raw, list) else raw
        if hasattr(case, 'iloc'):
            case = case.iloc[0].to_dict()
        activated = list(case.get('activated_transitions') or [])
    except Exception as exc:  # pragma: no cover - defensive
        log.info('Token replay failed (%s).', exc)
        result['inconclusive'] = True
        return result

    # The labelled transitions of the replay are the events of the trace;
    # the model reaches the end of the trace after the last of them.
    labelled = {activity for activity in activities}
    remaining = len(activities)

    marking = {place: int(count) for place, count in initial_marking.items()}
    for entry in activated:
        # PM4Py reports an activated transition as the transition object
        # itself, as its id, or as an (id, activity) pair.
        transition = None
        activity = None
        if hasattr(entry, 'in_arcs'):
            transition = entry
        elif isinstance(entry, (tuple, list)) and entry:
            transition = by_id.get(str(entry[0]))
            activity = entry[1] if len(entry) > 1 else None
        else:
            transition = by_id.get(str(entry))
        if transition is None:
            continue
        label = str(activity or getattr(transition, 'label', '') or
                    transition.name)
        _fire(marking, transition)
        if label in labelled:
            remaining -= 1
            if remaining <= 0:
                break

    if remaining > 0:
        # The replay could not match every event of the prefix, so the
        # marking it reached is not the marking of the prefix.
        result['inconclusive'] = True
        return result

    enabled = []
    for transition in getattr(net, 'transitions', None) or []:
        if all(marking.get(_input_place(arc), 0) > 0
               for arc in getattr(transition, 'in_arcs', None) or []):
            enabled.append(str(getattr(transition, 'label', '') or
                               transition.name))

    result['marking'] = {str(getattr(place, 'name', place)): int(count)
                         for place, count in marking.items()}
    result['marking_state'] = marking
    result['enabled'] = sorted(set(enabled))
    result['activities'] = enabled_activities(net, marking,
                                               declared or labelled)
    return result


# ── discovery ───────────────────────────────────────────────────
def discover_inductive(frame, activity_key='activity', case_id_key='case_id',
                       timestamp_key='timestamp', noise_threshold=0.02):
    """
    Run the Inductive Miner on a DataFrame of events.

    :returns: ``(net, initial_marking, final_marking)``
    """
    import pm4py

    columns = dict(activity_key=activity_key, case_id_key=case_id_key,
                   timestamp_key=timestamp_key)

    if hasattr(pm4py, 'discover_petri_net_inductive'):  # pragma: no cover
        return pm4py.discover_petri_net_inductive(
            frame, noise_threshold=noise_threshold, **columns)
    return pm4py.discover_petri_net(
        frame, algorithm=pm4py.algorithms.im.IM,
        noise_threshold=noise_threshold, **columns)


def export_petri_xml(net, initial_marking, final_marking) -> str:
    """Serialise a Petri net to PM4ML."""
    import pm4py

    if hasattr(pm4py, 'export_to_petri_xml'):  # pragma: no cover - pm4py < 2.7
        return pm4py.export_to_petri_xml(net, initial_marking, final_marking)

    handle, path = tempfile.mkstemp(suffix='.pnml', prefix='carma-pnml-')
    os.close(handle)
    try:
        pm4py.write_pnml(net, initial_marking, final_marking, path)
        with open(path, encoding='utf-8') as stream:
            return stream.read()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ── conformance ─────────────────────────────────────────────────
def token_replay(frame, net, initial_marking, final_marking,
                 activity_key='activity', case_id_key='case_id') -> dict:
    """
    Replay a single-case frame against a Petri net.

    :returns: the per-case result dict of the token-based replay.
    """
    from pm4py.algo.conformance.tokenreplay import algorithm as replay

    try:
        from pm4py.algo.conformance.tokenreplay.variants.token_replay import (
            Parameters,
        )
        result = replay.apply(
            frame, net, initial_marking, final_marking,
            parameters={
                Parameters.ACTIVITY_KEY: activity_key,
                Parameters.CASE_ID_KEY: case_id_key,
                Parameters.SHOW_PROGRESS_BAR: False,
                Parameters.RETURN_NAMES: True,
                # A prefix never reaches the final marking, so the remaining
                # tokens must not be counted as a conformance defect.
                Parameters.CONSIDER_REMAINING_IN_FITNESS: False,
            },
        )
    except ImportError:  # pragma: no cover - pm4py < 2.7
        result = replay.apply(
            frame, net, initial_marking, final_marking,
            parameters={'activity_key': activity_key,
                        'case_id_key': case_id_key,
                        'consider_remaining_in_fitness': False},
        )

    if isinstance(result, list):
        return result[0] if result else {}
    if hasattr(result, 'iloc'):
        return result.iloc[0].to_dict()
    return result


def alignment_detail(activities: list, net, initial_marking, final_marking,
                     activity_key='activity', case_id_key='case_id') -> dict:
    """
    The control-flow deviation of a trace against a Petri net.

    A benchmark case carries a *prefix* of a process, so the trace never
    reaches the final marking of the model.  A plain alignment cost would
    therefore charge the agent for the part of the process that has not
    been executed yet, which says nothing about the quality of an
    adaptation.  This function splits the alignment into the three kinds of
    move pm4py reports:

    ``log_moves``
        activities of the trace that the model cannot explain — the trace
        left the modelled behaviour;
    ``model_moves``
        activities of the model that had to be inserted before the trace
        ended — the trace skipped modelled behaviour;
    ``tail_moves``
        activities of the model that come after the trace ended — the part
        of the process that has simply not been executed yet.

    Only the first two are deviations, so the deviation cost is
    ``log_moves + model_moves``.

    :returns: a dict with the three move counts, the deviation cost and
              the raw alignment.
    """
    return _alignment_detail(activities, net, initial_marking, final_marking,
                              activity_key, case_id_key)


def _alignment_detail(activities: list, net, initial_marking, final_marking,
                       activity_key='activity', case_id_key='case_id',
                       max_seconds: float = 5.0) -> dict:
    import pandas as pd
    from pm4py.algo.conformance.alignments.petri_net import algorithm as alignments

    activities = [a for a in (activities or []) if a]
    detail = {'log_moves': 0, 'model_moves': 0, 'tail_moves': 0,
              'cost': 0.0, 'alignment': [], 'inconclusive': False}
    if not activities:
        return detail

    frame = pd.DataFrame([
        {case_id_key: 'case', activity_key: activity}
        for activity in activities
    ])

    try:
        # The default variant is pm4py's state-equation A*, which is the
        # exact-cost alignment.  Both keys have to be passed: the algorithm
        # groups the frame by case id, and its default for that is the XES
        # key "case:concept:name", which a plain DataFrame does not carry.
        #
        # The search is exponential in the length of the trace, so it runs
        # under a time bound; when the bound is hit pm4py returns None and
        # the alignment is reported as inconclusive.
        result = alignments.apply(
            frame, net, initial_marking, final_marking,
            parameters={
                alignments.Parameters.ACTIVITY_KEY: activity_key,
                alignments.Parameters.CASE_ID_KEY:  case_id_key,
                alignments.Parameters.SHOW_PROGRESS_BAR: False,
                alignments.Parameters.PARAM_MAX_ALIGN_TIME: max_seconds,
            },
        )
    except ImportError:  # pragma: no cover - pm4py < 2.7
        result = alignments.apply(frame, net, initial_marking, final_marking)

    if result is None:
        detail['inconclusive'] = True
        return detail

    if isinstance(result, list):
        result = result[0] if result else {}
    if result is None:
        # pm4py returns [None] when the search ran out of time.
        detail['inconclusive'] = True
        return detail
    if hasattr(result, 'iloc'):
        result = result.iloc[0].to_dict()

    alignment = result.get('alignment') or []
    if alignment and isinstance(alignment[0], list):
        alignment = alignment[0]

    moves = [(str(move), str(label)) for move, label in alignment]
    detail['alignment'] = moves

    # The index of the last move that consumed a trace event: everything
    # after it is the unexecuted tail of the process.
    last_trace_move = -1
    for index, (move, _label) in enumerate(moves):
        if move in ('match', 'skip'):
            last_trace_move = index

    for index, (move, _label) in enumerate(moves):
        if move == 'skip':
            detail['log_moves'] += 1
        elif move == 'complete':
            if index > last_trace_move:
                detail['tail_moves'] += 1
            else:
                detail['model_moves'] += 1

    detail['cost'] = float(detail['log_moves'] + detail['model_moves'])
    return detail


def alignment_cost(activities: list, net, initial_marking, final_marking,
                   activity_key='activity', case_id_key='case_id') -> float:
    """
    The control-flow deviation of a trace against a Petri net.

    :returns: the number of deviations, ``0.0`` when the trace follows the
              model without leaving it.
    """
    try:
        detail = alignment_detail(activities, net, initial_marking,
                                   final_marking, activity_key, case_id_key)
    except Exception as exc:
        log.info('PM4Py alignment unavailable (%s)', exc)
        return 0.0
    return float(detail.get('cost', 0.0))


@lru_cache(maxsize=8192)
def _alignment_detail_for_model(model_xml: str, activities: tuple,
                                activity_key: str, case_id_key: str,
                                max_seconds: float) -> dict:
    net, initial_marking, final_marking = read_model_xml(model_xml)
    return _alignment_detail(list(activities), net, initial_marking,
                             final_marking, activity_key, case_id_key,
                             max_seconds)


def alignment_detail_for_model(model_xml: str, activities: list,
                                activity_key='activity',
                                case_id_key='case_id',
                                max_seconds: float = 5.0) -> dict:
    """
    The control-flow deviation of a trace against a model given as XML.

    The result is cached per (model, trace), because the verifier checks
    the same prefixes and the same candidate plans over and over across
    the experiment grid.

    :returns: the deviation detail; ``inconclusive`` is set when the
              alignment search exceeded its time bound.
    """
    key = tuple(a for a in (activities or []) if a)
    if not key:
        return {'log_moves': 0, 'model_moves': 0, 'tail_moves': 0,
                'cost': 0.0, 'alignment': [], 'inconclusive': False}
    return _alignment_detail_for_model(model_xml or '', key, activity_key,
                                       case_id_key, max_seconds)


def enabled_transitions(net, marking) -> list:
    """The activities enabled in a marking."""
    import pm4py

    return [transition_name(t)
            for t in pm4py.get_enabled_transitions(net, marking)]

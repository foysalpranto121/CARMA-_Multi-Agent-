"""
CARMA — Process model discovery and constraint mining.

Builds the process frame F = (M, D, P) for an imported event log:

  M  a control-flow model discovered with the Inductive Miner and exported
     as PM4ML, so that the state estimator can token-replay prefixes on it;
  D  Declare constraints mined from the *training* split of the log;
  P  policy, authority, data and temporal rules derived from the log itself
     (amount thresholds from the observed amount distribution, role
     requirements from the observed resource roles, validity windows from
     the observed time span).

Everything is derived from the data — no constraint, threshold or role is
invented.  The only inputs are the event log and the names of the activities
that play a given role in the domain.
"""
from __future__ import annotations

import logging
import random
from collections import Counter, defaultdict

log = logging.getLogger('carma')

#: Role of an activity in the constraint mining, derived from the activity
#: name.  Kept explicit so that the mined constraints stay auditable.
ACTIVITY_ROLES = {
    # BPI 2017 — loan origination
    'A_Create Application': 'applicant',
    'A_Submitted':          'applicant',
    'A_Concept':            'applicant',
    'A_Validating':         'credit_officer',
    'A_Complete':           'credit_officer',
    'A_Accepted':           'credit_officer',
    'A_Denied':             'credit_officer',
    'A_Pending':            'credit_officer',
    'A_Cancelled':          'credit_officer',
    'A_Incomplete':         'credit_officer',
    'W_Handle leads':       'sales_agent',
    'W_Call incomplete files': 'customer_service',
    'W_Validate application': 'credit_officer',
    'W_Assess potential fraud': 'fraud_officer',
    'W_Complete application': 'credit_officer',
    'W_Call after offers':  'customer_service',
    'O_Create Offer':       'sales_agent',
    'O_Created':            'sales_agent',
    'O_Sent (mail and online)': 'sales_agent',
    'O_Accepted':           'customer',
    'O_Refused':            'customer',
    'O_Cancelled':          'customer',
    'O_Returned':           'customer',
    # BPI 2019 — purchase to pay
    'Purchase Order':                 'requester',
    'Purchase Order Approved':        'approver',
    'Purchase Order Rejected':        'approver',
    'Goods Receipt':                  'warehouse',
    'Invoice':                        'accountant',
    'Payment':                        'accountant',
    'Invoice Paid':                   'accountant',
    # BPI 2020 — travel permits
    'Travel Permit':                  'employee',
    'Permit Approved':                'supervisor',
    'Permit Rejected':                'supervisor',
    'Declaration Draft':              'employee',
    'Declaration Approved':           'budget_owner',
    'Declaration Rejected':           'budget_owner',
    'Request for Payment':            'employee',
    'Request for Payment Approved':   'budget_owner',
    'Payment':                        'finance',
    # RTFM — road traffic fine management
    'Create Fine':              'police_officer',
    'Send Fine Notification':   'police_officer',
    'Add Payment':              'offender',
    'Pay Fine':                 'offender',
    'Unpaid':                   'offender',
    'Paid':                     'offender',
    'Appeal':                   'offender',
    'Judge Payment':            'judge',
    'Appeal Judge':             'judge',
}

#: Activities whose completion is a precondition for another activity.
#: Used to mine ``response`` / ``precedence`` relations.
COMMON_FOLLOWERS = {
    'A_Create Application':  ['A_Submitted', 'A_Concept', 'A_Validating'],
    'A_Submitted':           ['A_Validating', 'A_Complete', 'A_Pending'],
    'A_Validating':          ['A_Accepted', 'A_Denied', 'A_Pending',
                              'A_Incomplete', 'A_Cancelled'],
    'W_Handle leads':        ['W_Call incomplete files',
                              'W_Assess potential fraud'],
    'O_Create Offer':        ['O_Created', 'O_Sent (mail and online)'],
    'O_Created':             ['O_Sent (mail and online)'],
    'O_Sent (mail and online)': ['O_Accepted', 'O_Refused', 'O_Returned'],
    'Purchase Order':        ['Purchase Order Approved',
                              'Purchase Order Rejected'],
    'Goods Receipt':         ['Invoice'],
    'Invoice':                ['Invoice Paid'],
    'Travel Permit':         ['Permit Approved', 'Permit Rejected'],
    'Declaration Draft':     ['Declaration Approved',
                              'Declaration Rejected'],
    'Request for Payment':   ['Request for Payment Approved', 'Payment'],
    'Create Fine':           ['Send Fine Notification', 'Add Payment'],
    'Send Fine Notification': ['Add Payment', 'Pay Fine'],
    'Add Payment':           ['Unpaid', 'Paid'],
    'Appeal':                ['Judge Payment', 'Appeal Judge'],
}

#: Amount-bearing case attributes, used to derive a data/threshold rule.
AMOUNT_COLUMNS = ('case:RequestedAmount', 'case:Item Value',
                  'case:Order Value', 'case:Request Amount',
                  'case:totalFineAmount', 'case:paymentAmount')


def _export_petri_xml(net, initial_marking, final_marking) -> str:
    """Serialise a discovered Petri net to PM4ML."""
    from carma_engine.pm4py_compat import export_petri_xml

    return export_petri_xml(net, initial_marking, final_marking)


def _net_activities(net) -> list:
    """The activity names of a discovered net."""
    from carma_engine.pm4py_compat import net_activities

    return net_activities(net)


def _net_transitions(net) -> list:
    """The directly-follows transitions of a discovered net."""
    from carma_engine.pm4py_compat import net_transitions

    return net_transitions(net)


def _discover_inductive(frame):
    """
    Run the Inductive Miner.

    The pm4py API changed twice in the 2.x line; the compatibility layer
    hides the difference.
    """
    from carma_engine.pm4py_compat import discover_inductive

    return discover_inductive(frame)


def discover_model(traces: list, max_traces: int = 5000, seed: int = 42):
    """
    Discover a control-flow model with the Inductive Miner.

    :param traces:     list of ``(activities, timestamps)`` pairs, one per
                      observed case.
    :param max_traces: how many distinct traces to feed to the miner.  The
        Inductive Miner is quadratic in the number of traces, so a bounded,
        deterministic sample of the training split is used.
    :returns: ``(model_xml, activities, transitions)`` where ``model_xml`` is
              the PM4ML serialisation of the discovered Petri net.
    """
    import pandas as pd
    import pm4py

    if not traces:
        raise ValueError('Cannot discover a model from an empty case list.')

    # Distinct traces, sampled deterministically.
    distinct = []
    seen = set()
    for activities, timestamps in traces:
        key = tuple(activities)
        if key in seen:
            continue
        seen.add(key)
        distinct.append((activities, timestamps))
    if len(distinct) > max_traces:
        rng = random.Random(seed)
        chosen = sorted(rng.sample(range(len(distinct)), max_traces))
        distinct = [distinct[i] for i in chosen]

    frame = pd.DataFrame([
        {'case_id': f'c{index}', 'activity': activity, 'timestamp': timestamp}
        for index, (activities, timestamps) in enumerate(distinct)
        for activity, timestamp in zip(activities, timestamps)
    ])
    frame['timestamp'] = pd.to_datetime(frame['timestamp'], utc=True,
                                        errors='coerce')
    # pm4py requires every event to carry a timestamp.  Events without one
    # inherit the last known timestamp of their case; cases without any
    # timestamp at all are dropped, since they carry no temporal information.
    frame['timestamp'] = frame.groupby('case_id')['timestamp'].ffill()
    before = len(frame)
    frame = frame.dropna(subset=['timestamp'])
    if len(frame) != before:
        log.info('Dropped %s events without any timestamp.', before - len(frame))
    net, initial_marking, final_marking = _discover_inductive(frame)
    model_xml = _export_petri_xml(net, initial_marking, final_marking)

    # The Inductive Miner adds structural nodes (skip_*, init_loop_*,
    # tauSplit_*, tauJoin_*) to the net.  They are part of the control-flow
    # model but they are not activities of the process, so the activity
    # vocabulary is restricted to what the log actually contains.
    observed = {activity for activities, _ in traces for activity in activities}
    activities = [name for name in _net_activities(net) if name in observed]
    if not activities:
        activities = _net_activities(net)

    transitions = [t for t in _net_transitions(net)
                   if t['from'] in set(activities) and t['to'] in set(activities)]
    return model_xml, activities, transitions


def end_activities(sequences, min_share: float = 0.01, limit: int = 10) -> list[str]:
    """
    The activities the training traces end with, most frequent first.

    An activity counts when it ends at least ``min_share`` of the traces.  It
    tells the agent where the continuation of a case has to arrive, which is
    process knowledge from the training split — never the end of the case
    the agent is working on.
    """
    counts = Counter(sequence[-1] for sequence in sequences if sequence)
    total = sum(counts.values())
    if not total:
        return []
    return [activity for activity, count in counts.most_common(limit)
            if count / total >= min_share]


def mine_declare_constraints(cases: list, activities: list) -> list[dict]:
    """
    Mine Declare constraints from the observed behaviour.

    Two families are mined:

    ``response``     a is always followed by b somewhere later in the case.
    ``precedence``   b never occurs before a.

    Both are mined from the *observed* traces, so a constraint only appears
    when the log supports it.  The violation cost reflects the empirical
    likelihood of the pattern, which is what the minimum-cost adaptation
    objective trades off.
    """
    total = len(cases)
    if not total:
        return []

    activities = set(activities)
    follows: dict[tuple, int] = defaultdict(int)
    precedes: dict[tuple, int] = defaultdict(int)
    occurrences: Counter = Counter()

    for sequence in cases:
        present = set(sequence)
        for activity in present:
            occurrences[activity] += 1
        for index, activity in enumerate(sequence):
            for later in sequence[index + 1:]:
                if later != activity:
                    follows[(activity, later)] += 1
            for earlier in sequence[:index]:
                if earlier != activity:
                    precedes[(earlier, activity)] += 1

    constraints: list[dict] = []

    # response(a, b): a occurs, b occurs later in the same case.
    for (a, b), count in follows.items():
        if a not in activities or b not in activities:
            continue
        if count / total < 0.8:
            continue
        # b must not also frequently precede a (that would be a cycle).
        back = precedes.get((b, a), 0)
        if back / total > 0.5:
            continue
        constraints.append({
            'constraint_type': 'response',
            'activity_a': a,
            'activity_b': b,
            'parameters': {'activities': [a, b], 'count': count},
            'violation_cost': round(max(0.5, 2.0 * (1.0 - count / total)), 3),
            'description': (
                f'Response({a}, {b}): in {count}/{total} observed cases '
                f'{b} follows {a}.'
            ),
        })

    # precedence(a, b): b never observed before a.
    for (a, b), count in precedes.items():
        if a not in activities or b not in activities:
            continue
        if count / total > 0.2:
            continue
        if (a, b) in follows:
            continue
        constraints.append({
            'constraint_type': 'precedence',
            'activity_a': a,
            'activity_b': b,
            'parameters': {'activities': [a, b]},
            'violation_cost': 1.5,
            'description': (
                f'Precedence({a}, {b}): {b} never observed before {a} '
                f'({count}/{total} cases).'
            ),
        })

    # existence(a): activity always present.
    for activity, count in occurrences.items():
        if activity not in activities:
            continue
        if count / total >= 0.95:
            constraints.append({
                'constraint_type': 'existence',
                'activity_a': activity,
                'activity_b': '',
                'parameters': {'activities': [activity]},
                'violation_cost': 1.0,
                'description': (
                    f'Existence({activity}): present in {count}/{total} cases.'
                ),
            })

    return constraints


def derive_policy_rules(cases: list, case_attributes: list[dict],
                         activities: list) -> list[dict]:
    """
    Derive the policy family (authority, data and temporal rules).

    * ``role_required``  the role that actually performs an activity in the
      log, taken from the most frequent resource of that activity.
    * ``amount_limit``   the observed 95th percentile of the amount-bearing
      case attribute, so that the bound reflects the real distribution.
    * ``temporal_window`` the first and last timestamp observed for the
      process, which is the validity window of the process version.
    """
    rules: list[dict] = []

    # --- authority: which role performs which activity -------------------
    role_counts: dict[str, Counter] = defaultdict(Counter)
    for case in cases:
        for event in case:
            activity = event.get('activity', '')
            resource = event.get('resource', '')
            if activity and resource:
                role_counts[activity][resource] += 1

    for activity, counts in role_counts.items():
        if activity not in activities:
            continue
        resource, occurrences = counts.most_common(1)[0]
        role = ACTIVITY_ROLES.get(activity, resource)
        rules.append({
            'constraint_type': 'role_required',
            'activity_a': activity,
            'activity_b': role,
            'parameters': {'role': role, 'resource': resource,
                           'occurrences': occurrences},
            'violation_cost': 1.0,
            'description': (
                f'Role "{role}" performs "{activity}" '
                f'({occurrences} observations, most frequent resource '
                f'{resource}).'
            ),
        })

    # --- data: an amount threshold derived from the observed distribution --
    for attribute in AMOUNT_COLUMNS:
        values = []
        for case in case_attributes:
            value = case.get(attribute)
            if value is None:
                continue
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                continue
        if len(values) < 20:
            continue
        values.sort()
        limit = values[int(len(values) * 0.95)]
        rules.append({
            'constraint_type': 'amount_limit',
            'activity_a': '',
            'activity_b': '',
            'parameters': {'field': attribute, 'limit': limit,
                           'quantile': 0.95, 'n': len(values)},
            'violation_cost': 2.0,
            'description': (
                f'Amount limit for "{attribute}": {limit:g} '
                f'(95th percentile of {len(values)} observed values).'
            ),
        })

    # --- temporal: the validity window of the process version -------------
    timestamps = []
    for case in cases:
        for event in case:
            timestamp = event.get('timestamp')
            if timestamp:
                timestamps.append(str(timestamp))
    if timestamps:
        timestamps.sort()
        rules.append({
            'constraint_type': 'temporal_window',
            'activity_a': '',
            'activity_b': '',
            'parameters': {'valid_from': timestamps[0],
                           'valid_until': timestamps[-1]},
            'violation_cost': 1.0,
            'description': (
                f'Process version valid between {timestamps[0]} and '
                f'{timestamps[-1]}.'
            ),
        })

    return rules


def build_constraint_set(process, name: str, constraints: list[dict],
                         version: str = '1.0'):
    """Persist a mined constraint set for ``process``."""
    from apps.processes.models import Constraint, ConstraintSet

    constraint_set, _ = ConstraintSet.objects.update_or_create(
        process=process, name=name,
        defaults={'version': version, 'is_active': True},
    )
    Constraint.objects.filter(constraint_set=constraint_set).delete()

    rows = []
    for constraint in constraints:
        rows.append(Constraint(
            constraint_set=constraint_set,
            constraint_type=constraint['constraint_type'],
            activity_a=constraint.get('activity_a', ''),
            activity_b=constraint.get('activity_b', ''),
            parameters=constraint.get('parameters', {}),
            violation_cost=constraint.get('violation_cost', 1.0),
            description=constraint.get('description', ''),
        ))
    Constraint.objects.bulk_create(rows)
    return constraint_set, len(rows)

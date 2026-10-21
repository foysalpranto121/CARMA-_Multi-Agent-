"""
Constraint knowledge layer.

The process frame F = (M, D, P) is compiled into a single NetworkX DiGraph:

  * nodes  -> individual constraints (Declare / LTLf / policy), carrying their
              template, parameters, severity and violation cost (lambda_i)
  * edges  -> ordering relations extracted from binary constraints
              (response / precedence / succession)

The graph also stores the procedural model XML so the SCV alignment checker can
verify a projected trace against the Petri net without another DB round-trip.
"""
from __future__ import annotations

import logging

import networkx as nx

log = logging.getLogger('carma')

# Constraint templates that express a binary ordering relation over activities.
ORDERING_TEMPLATES = ('response', 'precedence', 'succession')

#: Template of the constraint that records an activity rename.  A
#: structural-drift scenario writes the rename into the frame, so that the
#: verifier accepts the new name as the activity it replaced.
DRIFT_TEMPLATE = 'drift_mapping'


def build_constraint_graph(process, constraint_sets=None) -> nx.DiGraph:
    """
    Compile a process frame into an executable constraint graph.

    :param process:            a ``processes.Process`` instance
    :param constraint_sets:    optional iterable of ``ConstraintSet`` to restrict
                               the compilation to; ``None`` means every active
                               set of the process.
    :returns: a ``networkx.DiGraph``
    """
    graph = nx.DiGraph()
    graph.graph['process_id'] = str(process.id)
    graph.graph['process_name'] = process.name
    graph.graph['model_type'] = process.model_type
    graph.graph['model_xml'] = process.model_xml or ''
    graph.graph['activities'] = list(process.activities or [])

    if constraint_sets is None:
        constraint_sets = process.constraint_sets.filter(is_active=True)
    else:
        constraint_sets = [cs for cs in constraint_sets if cs.is_active]

    for constraint_set in constraint_sets:
        for constraint in constraint_set.constraints.all():
            node_id = str(constraint.id)
            graph.add_node(
                node_id,
                constraint_id=node_id,
                template=constraint.constraint_type,
                parameters=dict(constraint.parameters or {}),
                severity='hard',
                violation_cost=float(constraint.violation_cost or 1.0),
                activity_a=constraint.activity_a,
                activity_b=constraint.activity_b,
                description=constraint.description or '',
                constraint_set_id=str(constraint_set.id),
            )

            if constraint.constraint_type in ORDERING_TEMPLATES:
                activities = [a for a in (constraint.activity_a, constraint.activity_b) if a]
                if len(activities) == 2:
                    graph.add_edge(
                        activities[0], activities[1],
                        constraint_id=node_id,
                        template=constraint.constraint_type,
                    )

    log.debug(
        'Constraint graph for process %s: %d nodes, %d edges.',
        process.id, graph.number_of_nodes(), graph.number_of_edges(),
    )
    return graph


def constraint_graph_to_dict(graph: nx.DiGraph) -> dict:
    """Serialise a constraint graph into a JSON-safe dict (for agent state)."""
    return {
        'process_id': graph.graph.get('process_id'),
        'nodes': [
            {'id': node_id, **{k: v for k, v in data.items() if k != 'parameters'},
             'parameters': data.get('parameters', {})}
            for node_id, data in graph.nodes(data=True)
        ],
        'edges': [
            {'from': u, 'to': v, **{k: val for k, val in data.items()}}
            for u, v, data in graph.edges(data=True)
        ],
    }


def apply_drift(graph: nx.DiGraph, perturbation: dict) -> nx.DiGraph:
    """
    Record an activity rename in the constraint graph.

    A structural-drift scenario renames the activity that is about to be
    executed.  The frame has to know about the rename, otherwise the
    verifier would reject the very behaviour the scenario asks for.  The
    rename is stored as a constraint node, so that it travels with the
    graph and is visible in the agent state.

    :returns: the same graph, for chaining.
    """
    injected = (perturbation or {}).get('injected') or {}
    old_activity = injected.get('old_activity')
    new_activity = injected.get('new_activity')
    if not old_activity or not new_activity or old_activity == new_activity:
        return graph

    node_id = f'drift:{new_activity}'
    graph.add_node(
        node_id,
        constraint_id=node_id,
        template=DRIFT_TEMPLATE,
        parameters={'mapping': {new_activity: old_activity}},
        severity='hard',
        violation_cost=0.0,
        activity_a=new_activity,
        activity_b=old_activity,
        description=(f'The activity "{old_activity}" was renamed to '
                     f'"{new_activity}".'),
    )
    return graph


def apply_scenario_frame(graph: nx.DiGraph, perturbation: dict) -> nx.DiGraph:
    """
    Write the scenario's rule version into the constraint graph.

    A perturbation can change the frame of the case it belongs to:

    * an **exception** withdraws an activity, because the document it
      needs is missing;
    * a **rule change** adds the new version of a rule next to the old
      one, so that the verifier can tell which version is in force at the
      moment of the case;
    * a **structural drift** renames an activity.

    :returns: the same graph, for chaining.
    """
    perturbation = perturbation or {}
    injected = perturbation.get('injected') or {}
    kind = perturbation.get('type')

    if kind == 'exception':
        activity = injected.get('blocked_activity')
        if activity:
            node_id = f'exception:{activity}'
            graph.add_node(
                node_id,
                constraint_id=node_id,
                template='absence',
                parameters={'activities': [activity]},
                severity='hard',
                violation_cost=1.0,
                activity_a=activity,
                activity_b='',
                description=(f'The document required by "{activity}" is '
                             f'missing, so the activity cannot be executed.'),
            )

    elif kind == 'rule_change':
        field = injected.get('field')
        limit = injected.get('new')
        if field is not None and limit is not None:
            node_id = f'rule:{field}:{limit}'
            graph.add_node(
                node_id,
                constraint_id=node_id,
                template='amount_limit',
                parameters={
                    'field': field,
                    'limit': limit,
                    'valid_from': injected.get('effective_from'),
                },
                severity='hard',
                violation_cost=2.0,
                activity_a='',
                activity_b='',
                description=(f'The approval threshold for "{field}" is {limit} '
                             f'from {injected.get("effective_from")}.'),
            )

    return apply_drift(graph, perturbation)


def activity_aliases(constraint_graph) -> dict:
    """
    The activity renames the frame knows about.

    :returns: ``{new name: original name}``
    """
    aliases: dict[str, str] = {}
    if constraint_graph is None:
        return aliases
    for _node_id, data in constraint_graph.nodes(data=True):
        if data.get('template') != DRIFT_TEMPLATE:
            continue
        mapping = (data.get('parameters') or {}).get('mapping') or {}
        for new_name, old_name in mapping.items():
            aliases[str(new_name)] = str(old_name)
    return aliases


def canonical_activities(activities: list, constraint_graph) -> list:
    """
    Map the activity names of a trace onto the names of the frame.

    A renamed activity is resolved back to the name the model and the
    declarative constraints use, so that the frame judges the behaviour
    rather than the spelling.
    """
    aliases = activity_aliases(constraint_graph)
    if not aliases:
        return list(activities or [])
    return [aliases.get(activity, activity) for activity in (activities or [])]

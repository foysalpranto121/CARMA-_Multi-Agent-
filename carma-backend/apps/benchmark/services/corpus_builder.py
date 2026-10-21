"""
CARMA — SOP corpus builder.

The constraint-aware retriever needs a knowledge corpus K to retrieve from.
For the benchmark this corpus is built from the *training* split of the
imported log, so the agent never sees the test cases it is evaluated on.

The corpus deliberately contains the failure modes the study is about:

* documents tagged with the stage they belong to, so that a document of the
  wrong stage is retrievable but must be filtered out by the CAR filter;
* superseded versions of a document, so that an outdated rule is retrievable
  but must be filtered out by the validity check;
* rule cards for the mined constraints, so that the declarative frame D and
  the policy rules P reach the agent as *retrievable knowledge* — the
  channel the retrieval factor of the design is about;
* historical cases, which are the precedents the retriever is supposed to
  find.
"""
from __future__ import annotations

import logging
from collections import defaultdict

log = logging.getLogger('carma')

#: The version boundary of the corpus.  The superseded version of a
#: document stopped applying when the observed period of the log begins, so
#: the temporal filter of the CAR retriever has a real decision to make:
#: every benchmark case is dated after that moment.
CORPUS_VALID_FROM = '2016-01-01T00:00:00'
CORPUS_VALID_UNTIL = '2016-06-01T00:00:00'


def build_corpus(process, event_log, cases, max_documents: int = 400,
                 max_precedents: int = 200, constraint_set=None) -> int:
    """
    Build the SOP corpus of a process from its training cases.

    :param process:        the ``Process`` the corpus belongs to
    :param event_log:      the ``EventLog`` the cases come from
    :param cases:          the training-split ``Case`` rows
    :param max_documents:  how many SOP documents to generate
    :param max_precedents: how many historical cases to store
    :param constraint_set: the mined constraint set, rendered as rule cards
    :returns: the number of corpus documents written
    """
    from apps.processes.models import CorpusDocument

    CorpusDocument.objects.filter(process=process).delete()

    activities = [a for a in (process.activities or [])]
    if not activities:
        return 0

    # Group the training traces by their activity sequence so that the
    # corpus reflects the variants that actually occur.
    by_prefix: dict[tuple, list] = defaultdict(list)
    for case in cases:
        sequence = tuple(event.get('activity', '')
                         for event in (case.prefix_trace or []))
        by_prefix[sequence].append(case)

    # The moment the observed period of the log begins.  The superseded
    # version of a document stopped applying at that moment, so every
    # benchmark case — training and test alike — is dated after the end of
    # its validity window.
    timestamps = sorted(
        str(event.get('timestamp'))
        for case in cases
        for event in (case.prefix_trace or [])
        if event.get('timestamp')
    )
    superseded_until = timestamps[0] if timestamps else CORPUS_VALID_UNTIL

    # --- SOP documents, one per (activity, role) pair of the process -----
    role_of = {}
    from apps.processes.models import Constraint
    for constraint in Constraint.objects.filter(
            constraint_set__process=process,
            constraint_set__is_active=True,
            constraint_type='role_required'):
        if constraint.activity_a and constraint.parameters.get('role'):
            role_of[constraint.activity_a] = constraint.parameters['role']

    documents = []
    for activity in activities:
        role = role_of.get(activity, 'system')
        observed = sum(1 for sequence in by_prefix if activity in sequence)
        documents.append({
            'title':     f'SOP: {activity}',
            'doc_type':  'sop',
            'content': (
                f'Activity "{activity}" is performed in the role "{role}". '
                f'Preconditions: the preceding activity of the process has '
                f'been completed. '
                f'Observed in {observed} of the {len(by_prefix)} distinct '
                f'trace variants of the training split.'
            ),
            'stage':     activity,
            'metadata': {
                'activity':      activity,
                'activity_tags': [activity],
                'role':          role,
                'role_tags':     [role],
                'validity':      'current',
                'valid_from':    CORPUS_VALID_FROM,
                'valid_until':   None,
                'observed_cases': observed,
            },
        })
        # A superseded version of the same document, so that the retriever
        # has an outdated rule to filter out.  It carries the validity
        # window that ends before the cases of the benchmark start, so the
        # temporal filter of the CAR retriever can rule it out while a
        # plain vector ranking keeps it in the candidate set.
        documents.append({
            'title':     f'SOP: {activity} (version 1, superseded)',
            'doc_type':  'sop',
            'content': (
                f'Older version of the standard operating procedure for '
                f'"{activity}". This version predates the current process '
                f'and no longer applies.'
            ),
            'stage':     activity,
            'metadata': {
                'activity':      activity,
                'activity_tags': [activity],
                'role':          role,
                'role_tags':     [role],
                'validity':      'superseded',
                'valid_from':    None,
                'valid_until':   superseded_until,
            },
        })

    # --- rule cards: the mined frame as retrievable knowledge -----------
    # The declarative constraints D and the policy rules P reach the agent
    # through retrieval.  A rule card is the natural-language rendering of
    # one mined constraint, tagged with the activities it binds, so that the
    # constraint-aware retriever can match it against the constraints that
    # are in force at the current state of the case.
    documents.extend(_rule_cards(constraint_set, role_of))

    for index, (sequence, group) in enumerate(
            sorted(by_prefix.items(), key=lambda item: -len(item[1]))):
        if len(documents) >= max_documents:
            break
        if not sequence:
            continue
        documents.append({
            'title':     f'Historical case {group[0].case_id}',
            'doc_type':  'case',
            'content': (
                'Observed case with the activity sequence: '
                + ' -> '.join(sequence)
                + '. This is a precedent from the training split.'
            ),
            'stage':     sequence[-1],
            'metadata': {
                'case_id':   group[0].case_id,
                'sequence':  list(sequence),
                'length':    len(sequence),
                'frequency': len(group),
                'validity':  'precedent',
                'activity_tags': [activity for activity in sequence[-3:]],
            },
        })

    for index, (sequence, group) in enumerate(
            sorted(by_prefix.items(), key=lambda item: -len(item[1]))):
        if index >= max_precedents:
            break
        if not sequence:
            continue
        documents.append({
            'title':     f'Requirement: {sequence[-1]} follows {sequence[0]}',
            'doc_type':  'policy',
            'content': (
                f'Policy derived from the training split: the sequence '
                f'{" -> ".join(sequence)} was observed '
                f'{len(group)} times.'
            ),
            'stage':     sequence[-1],
            'metadata': {
                'activity': sequence[-1],
                'activity_tags': [sequence[-1]],
                'sequence': list(sequence),
                'validity': 'current',
                'valid_from': CORPUS_VALID_FROM,
            },
        })

    CorpusDocument.objects.bulk_create([
        CorpusDocument(
            process=process,
            title=document['title'],
            doc_type=document['doc_type'],
            content=document['content'],
            stage=document['stage'],
            timestamp=None,
            metadata=document['metadata'],
        )
        for document in documents
    ], batch_size=200)

    log.info('Built %s corpus documents for process %s.',
             len(documents), process.name)
    return len(documents)


#: How a mined constraint is phrased for a human reader.  The agent reads
#: the rule card, so the wording has to carry the same content as the
#: constraint it stands for.
TEMPLATE_PHRASES = {
    'response': ('When "{a}" has been performed, "{b}" must be performed '
                 'before the case can end.'),
    'precedence': ('"{b}" may only be performed after "{a}" has been '
                   'performed.'),
    'succession': ('"{a}" and "{b}" must alternate: "{a}" is performed '
                   'before "{b}".'),
    'not_coexistence': ('"{a}" and "{b}" must never occur in the same case.'),
    'existence': ('"{a}" must be performed at least once in the case.'),
    'absence': ('"{a}" must not be performed in the case.'),
    'exactly': ('"{a}" must be performed exactly {count} times in the case.'),
    'init': ('The case starts with "{a}".'),
    'role_required': ('"{a}" is performed by the role "{role}".'),
    'amount_limit': ('The amount of "{a}" must not exceed {limit}.'),
    'temporal_window': ('"{a}" must be performed between {start} and {end}.'),
}


def _rule_cards(constraint_set, role_of: dict) -> list[dict]:
    """
    Render the mined constraint set as retrievable rule cards.

    Every card carries the activities it binds as activity tags and the
    validity window of the rule version, which is what lets the
    constraint-aware retriever match a document against the constraints
    that are in force at the current state of a case.
    """
    if constraint_set is None:
        return []

    cards: list[dict] = []
    for constraint in constraint_set.constraints.all():
        template = constraint.constraint_type
        phrase = TEMPLATE_PHRASES.get(template)
        if not phrase:
            continue
        params = dict(constraint.parameters or {})
        a = constraint.activity_a or ''
        b = constraint.activity_b or ''
        role = params.get('role') or role_of.get(a) or ''
        try:
            content = phrase.format(a=a, b=b, role=role,
                                    count=params.get('count', 1),
                                    limit=params.get('limit', ''),
                                    start=params.get('start', ''),
                                    end=params.get('end', ''))
        except (KeyError, IndexError, ValueError):
            content = constraint.description or template

        tags = [activity for activity in (a, b) if activity]
        valid_from = params.get('valid_from')
        valid_until = params.get('valid_until')
        cards.append({
            'title':     f'Rule: {template}({a}' + (f', {b}' if b else '') + ')',
            'doc_type':  'rule',
            'content': (
                f'{content} '
                f'{constraint.description or ""}'.strip()
            ),
            'stage':     a or (tags[0] if tags else ''),
            'metadata': {
                'constraint_id': str(constraint.id),
                'template':      template,
                'activity':      a,
                'activity_tags': tags,
                'role_tags':     [role] if role else [],
                'validity':      'current' if valid_from else 'current',
                'valid_from':    valid_from,
                'valid_until':   valid_until,
            },
        })

        # A stale version of the same rule: it binds the same activities,
        # so a similarity ranking cannot tell the two apart — only the
        # validity window can.
        if valid_from:
            cards.append({
                'title':     f'Rule: {template}({a}'
                             + (f', {b}' if b else '') + ') (previous version)',
                'doc_type':  'rule',
                'content': (
                    f'Previous version of the rule. {content} '
                    f'This version was replaced and no longer applies.'
                ),
                'stage':     a or (tags[0] if tags else ''),
                'metadata': {
                    'constraint_id': str(constraint.id),
                    'template':      template,
                    'activity':      a,
                    'activity_tags': tags,
                    'role_tags':     [role] if role else [],
                    'validity':      'superseded',
                    'valid_from':    None,
                    'valid_until':   valid_from,
                },
            })
    return cards

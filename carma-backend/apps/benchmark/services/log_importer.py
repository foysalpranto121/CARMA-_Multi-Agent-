"""
CARMA — WF-Adapt event log importer.

Reads a public BPI XES event log, splits it by time and persists the
resulting process instances as ``Case`` rows.

The importer is written against the pm4py 2.7 DataFrame API
(``pm4py.read_xes`` returns a ``pandas.DataFrame`` with one row per event),
but falls back to the legacy event-log object API so that the module keeps
working with older pm4py releases.

Only ``lifecycle:transition == 'complete'`` events are kept: the BPI logs
record every workflow state change (schedule, start, suspend, resume) as a
separate event, and those are noise for conformance checking — the activity
sequence of a case is the sequence of its *completed* activities.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger('carma')

#: Column names used by the different log families.
CASE_COLUMNS = ('case:concept:name', 'case_id', 'concept:name')
TIME_COLUMNS = ('time:timestamp', 'time:timestamp ')
ACTIVITY_COLUMNS = ('concept:name', 'activity')
RESOURCE_COLUMNS = ('org:resource', 'user')
LIFECYCLE_COLUMNS = ('lifecycle:transition', 'lifecycle')

#: Where the raw event logs live.  ``CARMA_DATA_DIR`` overrides the default.
DEFAULT_DATA_DIR = os.path.join(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))),
    'data',
)


@dataclass(frozen=True)
class LogSpec:
    """Description of one supported public event log."""
    key: str
    display_name: str
    domain: str
    filename: str
    split_ratio: float = 0.7
    description: str = ''
    #: Case-level columns copied into ``Case.attributes``.
    case_attributes: tuple = ()
    #: Activities that carry a document/evidence request in this log.
    document_activities: tuple = ()
    #: Activities that represent a decision/approval step.
    decision_activities: tuple = ()
    #: Activities that represent a payment/disbursement step.
    payment_activities: tuple = ()


SUPPORTED_LOGS: dict[str, LogSpec] = {
    'bpi2017': LogSpec(
        key='bpi2017',
        display_name='BPI Challenge 2017 — Loan Application',
        domain='loan origination',
        filename='BPI_Challenge_2017.xes',
        description=(
            'Real-life event log of a Dutch financial institute: all loan '
            'applications filed through an online system in 2016, covering '
            'the application, workflow and offer origins.'
        ),
        case_attributes=('case:RequestedAmount', 'case:LoanGoal',
                         'case:ApplicationType'),
        document_activities=('W_Call incomplete files',),
        decision_activities=('A_Validating', 'A_Accepted', 'A_Denied',
                             'A_Pending', 'A_Cancelled', 'A_Incomplete',
                             'A_Complete', 'A_Concept'),
        payment_activities=('O_Create Offer', 'O_Created', 'O_Accepted',
                            'O_Refused', 'O_Cancelled', 'O_Returned',
                            'O_Sent (mail and online)'),
    ),
    'bpi2019': LogSpec(
        key='bpi2019',
        display_name='BPI Challenge 2019 — Purchase-to-Pay',
        domain='purchase-to-pay',
        filename='BPI_Challenge_2019.xes',
        description=(
            'Real-life event log of a multinational company in the coatings '
            'and paints sector, covering purchase orders with line items and '
            'a three-way match between order, goods receipt and invoice.'
        ),
        case_attributes=('case:Item Value', 'case:Item Currency',
                         'case:Item Name', 'case:Order Value',
                         'case:Supplier', 'case:Gross Value'),
        document_activities=('Purchase Order', 'Goods Receipt',
                             'Invoice'),
        decision_activities=('Purchase Order Approved',
                             'Purchase Order Rejected'),
        payment_activities=('Payment', 'Invoice Paid'),
    ),
    'bpi2020': LogSpec(
        key='bpi2020',
        display_name='BPI Challenge 2020 — Travel Permit',
        domain='travel expense reimbursement',
        filename='PermitLog.xes',
        description=(
            'Real-life event log of the travel-permit and travel-expense '
            'reimbursement process of a university, covering permits, '
            'declarations and requests for payment over two years.'
        ),
        case_attributes=('case:Request Amount', 'case:Cost Center',
                         'case:Organization', 'case:Department'),
        document_activities=('Declaration Draft', 'Travel Permit',
                              'Request for Payment'),
        decision_activities=('Permit Approved', 'Permit Rejected',
                             'Declaration Approved', 'Declaration Rejected'),
        payment_activities=('Payment', 'Request for Payment Approved'),
    ),
    'rtfm': LogSpec(
        key='rtfm',
        display_name='Road Traffic Fine Management',
        domain='public administration fines',
        filename='Road_Traffic_Fine_Management.xes',
        description=(
            'Real-life event log of an information system managing road '
            'traffic fines: creation, payment, appeal and collection of '
            'fines by a municipal authority.'
        ),
        case_attributes=('case:vehicleClass', 'case:totalFineAmount',
                         'case:paymentAmount', 'case:expense'),
        document_activities=('Send Fine Notification', 'Add Payment',
                             'Appeal'),
        decision_activities=('Unpaid', 'Paid', 'Judge Payment',
                             'Appeal Judge'),
        payment_activities=('Pay Fine', 'Payment', 'Add Payment'),
    ),
    # The light replacement for BPI 2019 (about 700 MB): 14 MB, 4,580 tickets.
    # Source: Polato, M. (2017) "Dataset belonging to the help desk log of an
    # Italian company", Mendeley Data, doi:10.17632/39bp3vv62t.1; the XES is
    # the conversion shipped with pm4py (tests/input_data/helpdesk.xes.gz).
    'helpdesk': LogSpec(
        key='helpdesk',
        display_name='Helpdesk — IT Service Tickets',
        domain='IT service management',
        filename='Helpdesk.xes',
        description=(
            'Real-life event log of the ticketing system of the help desk of an '
            'Italian software company: every ticket from its insertion to its '
            'closure, 2010-2014.'
        ),
        case_attributes=('seriousness', 'service_level', 'service_type',
                         'product', 'customer'),
        document_activities=('Insert ticket', 'Create SW anomaly'),
        # The steps after which the ticket can still go several ways.
        decision_activities=('Assign seriousness', 'Take in charge ticket', 'Wait'),
        payment_activities=(),
    ),
}


@dataclass
class ImportedCase:
    """One process instance extracted from an event log."""
    case_id: str
    activities: list = field(default_factory=list)
    attributes: dict = field(default_factory=dict)
    start_time: str = ''
    end_time: str = ''
    split: str = 'train'


#: Logs downloaded by hand go here; this folder is searched before ``data``.
DOWNLOAD_DATA_DIR = os.path.join(os.path.dirname(DEFAULT_DATA_DIR), 'dataset')


def data_dirs() -> list[str]:
    """
    The folders the raw event logs are looked up in, in order:
    ``CARMA_DATA_DIR`` (environment or ``.env``), ``dataset``, ``data``.
    """
    try:
        from decouple import config  # noqa: PLC0415
        configured = config('CARMA_DATA_DIR', default='')
    except ImportError:  # pragma: no cover - python-decouple is a core requirement
        configured = os.environ.get('CARMA_DATA_DIR', '')
    return ([configured] if configured else []) + [DOWNLOAD_DATA_DIR, DEFAULT_DATA_DIR]


def data_dir() -> str:
    return data_dirs()[0]


def log_path(dataset_key: str) -> str:
    """Absolute path of the XES file backing ``dataset_key`` (the first folder that has it)."""
    spec = SUPPORTED_LOGS[dataset_key]
    for directory in data_dirs():
        path = os.path.join(directory, spec.filename)
        if os.path.exists(path):
            return path
    return os.path.join(data_dir(), spec.filename)


def _first_present(columns, candidates):
    for name in candidates:
        if name in columns:
            return name
    return None


def read_xes_frame(path: str):
    """
    Read a XES file into a ``pandas.DataFrame`` of events.

    Works with both the pm4py 2.7 DataFrame API and the legacy event-log
    object API, returning a DataFrame either way.
    """
    import pandas as pd
    import pm4py

    raw = pm4py.read_xes(path, show_progress_bar=False)

    if isinstance(raw, pd.DataFrame):
        return raw

    # Legacy API: rebuild a DataFrame from the event-log object.
    rows = []
    for trace in raw:
        case_attributes = dict(getattr(trace, 'attributes', {}) or {})
        for event in trace:
            row = dict(getattr(event, 'attributes', {}) or {})
            row.update({k: v for k, v in case_attributes.items()
                        if k not in row})
            rows.append(row)
    return pd.DataFrame(rows)


def _normalise_frame(df, spec: LogSpec):
    """Project a raw event DataFrame onto the canonical column names."""
    import pandas as pd

    df = df.copy()
    columns = list(df.columns)

    case_col = _first_present(columns, CASE_COLUMNS)
    time_col = _first_present(columns, TIME_COLUMNS)
    act_col = _first_present(columns, ACTIVITY_COLUMNS)
    res_col = _first_present(columns, RESOURCE_COLUMNS)
    life_col = _first_present(columns, LIFECYCLE_COLUMNS)

    if case_col is None or act_col is None:
        raise ValueError(
            f'Event log has no case identifier and/or activity column. '
            f'Columns found: {columns[:20]}'
        )

    out = pd.DataFrame()
    out['case_id'] = df[case_col].astype(str)
    out['activity'] = df[act_col].astype(str)
    out['time'] = (df[time_col] if time_col is not None
                   else pd.Series(pd.NaT, index=df.index))
    out['resource'] = (df[res_col].astype(str) if res_col is not None
                       else pd.Series('', index=df.index))
    out['lifecycle'] = (df[life_col].astype(str) if life_col is not None
                         else pd.Series('complete', index=df.index))
    out['origin'] = (df['EventOrigin'].astype(str)
                     if 'EventOrigin' in columns
                     else pd.Series('', index=df.index))

    # Case-level attributes are constant within a case, so they are carried
    # through as extra columns and picked up once per case.
    for column in spec.case_attributes:
        if column in columns:
            out[f'attr:{column}'] = df[column]
    return out


def extract_cases(df, spec: LogSpec, keep_lifecycle: tuple = ('complete',)):
    """
    Group a normalised event frame into per-case traces.

    ``keep_lifecycle`` selects which ``lifecycle:transition`` values count as
    a real activity.  Lifecycle noise (schedule/start/resume) is dropped by
    default.
    """
    import pandas as pd

    if keep_lifecycle:
        mask = df['lifecycle'].str.lower().isin(keep_lifecycle)
        df = df[mask]

    df = df.sort_values(['case_id', 'time'], kind='stable')

    attribute_columns = [c for c in df.columns if c.startswith('attr:')]

    cases: dict[str, ImportedCase] = {}
    for case_id, group in df.groupby('case_id', sort=False):
        activities = []
        for _, row in group.iterrows():
            activities.append(_json_safe({
                'activity':    row['activity'],
                'timestamp':   _iso(row['time']),
                'resource':    row['resource'],
                'origin':      row['origin'],
            }))
        if not activities:
            continue

        attributes = {}
        for column in attribute_columns:
            value = group[column].dropna()
            if len(value):
                attributes[column[len('attr:'):]] = _scalar(value.iloc[0])

        cases[case_id] = ImportedCase(
            case_id=str(case_id),
            activities=activities,
            attributes=_json_safe(attributes),
            start_time=activities[0]['timestamp'],
            end_time=activities[-1]['timestamp'],
        )
    return cases


#: Above this size an XES file is streamed trace by trace instead of being
#: read into one event DataFrame: pm4py's reader needs several times the file
#: size in memory, and BPI 2019 (about 700 MB) does not fit into 8 GB.
STREAM_THRESHOLD_BYTES = 300 * 1024 * 1024

_XES_VALUE_TAGS = ('string', 'date', 'int', 'float', 'boolean', 'id')


def _local(tag: str) -> str:
    """The tag without its XML namespace."""
    return tag.rsplit('}', 1)[-1]


def _xes_value(tag: str, raw: str):
    """A typed XES attribute value as the XES reader types it."""
    if tag == 'int':
        try:
            return int(raw)
        except ValueError:
            return None
    if tag == 'float':
        try:
            value = float(raw)
        except ValueError:
            return None
        return None if value != value else value
    if tag == 'boolean':
        return raw.strip().lower() == 'true'
    return raw


def _timestamp(raw: str | None):
    """
    A XES date as pm4py reads it.

    pm4py keeps the wall-clock time written in the log and labels it UTC —
    it drops the offset instead of converting.  The logs read through pm4py
    carry their timestamps that way, so this reader does the same and every
    log of the benchmark shares one convention.
    """
    import pandas as pd

    if not raw:
        return None
    try:
        stamp = pd.Timestamp(raw)
    except (ValueError, TypeError):
        return None
    if stamp.tzinfo is not None:
        stamp = stamp.tz_localize(None)
    return stamp.tz_localize('UTC')


def stream_xes_cases(path: str, spec: LogSpec,
                     keep_lifecycle: tuple = ('complete',)) -> dict:
    """
    Read a XES file trace by trace and build the cases directly.

    Produces what ``extract_cases(_normalise_frame(read_xes_frame(path), spec))``
    produces, without materialising one row per event for the whole log:
    each trace element is released as soon as its case has been built.

    :raises ValueError: when the file is not a complete XES document (an
        interrupted download ends in the middle of an element)
    """
    import xml.etree.ElementTree as ET

    wanted = {name[len('case:'):]: name for name in spec.case_attributes
              if name.startswith('case:')}
    keep = {value.lower() for value in keep_lifecycle} if keep_lifecycle else None
    cases: dict[str, ImportedCase] = {}
    stack: list[str] = []
    trace_attrs: dict = {}
    events: list = []
    event: dict | None = None

    try:
        for kind, element in ET.iterparse(path, events=('start', 'end')):
            tag = _local(element.tag)
            if kind == 'start':
                stack.append(tag)
                if tag == 'trace':
                    trace_attrs, events = {}, []
                elif tag == 'event':
                    event = {}
                continue

            stack.pop()
            parent = stack[-1] if stack else ''
            if tag in _XES_VALUE_TAGS:
                value = (tag, element.get('value', ''))
                if parent == 'event' and event is not None:
                    event[element.get('key')] = value
                elif parent == 'trace':
                    trace_attrs[element.get('key')] = value
            elif tag == 'event':
                if event is not None:
                    events.append(event)
                event = None
                element.clear()
            elif tag == 'trace':
                case = _case_from_trace(trace_attrs, events, wanted, keep)
                if case is not None:
                    cases[case.case_id] = case
                element.clear()
    except ET.ParseError as exc:
        raise ValueError(
            f'{path} is not a complete XES file ({exc}). Download it again with '
            f'scripts/fetch_event_logs.ps1.'
        ) from exc
    return cases


def _case_from_trace(trace_attrs: dict, events: list, wanted: dict, keep) -> ImportedCase | None:
    name = trace_attrs.get('concept:name')
    if name is None:
        return None

    rows = []
    for position, attrs in enumerate(events):
        lifecycle = (attrs.get('lifecycle:transition') or ('string', 'complete'))[1]
        if keep is not None and lifecycle.lower() not in keep:
            continue
        activity = attrs.get('concept:name')
        if activity is None:
            continue
        resource = attrs.get('org:resource') or attrs.get('user')
        origin = attrs.get('EventOrigin')
        rows.append((_timestamp((attrs.get('time:timestamp') or ('date', ''))[1]), position, {
            'activity':  activity[1],
            # pm4py reads an event without a resource as a missing value.
            'resource':  resource[1] if resource else None,
            'origin':    origin[1] if origin else '',
        }))
    if not rows:
        return None

    # Within a case the events run in time order; events without a time go
    # last and ties keep the order of the file (a stable sort).
    rows.sort(key=lambda row: (row[0] is None, row[0] if row[0] is not None else 0, row[1]))
    activities = []
    for stamp, _, row in rows:
        activities.append(_json_safe({
            'activity':  row['activity'],
            'timestamp': _iso(stamp),
            'resource':  row['resource'],
            'origin':    row['origin'],
        }))

    attributes = {}
    for key, column in wanted.items():
        if key in trace_attrs:
            tag, raw = trace_attrs[key]
            value = _xes_value(tag, raw)
            if value is not None:
                attributes[column] = value

    return ImportedCase(
        case_id=str(name[1]),
        activities=activities,
        attributes=_json_safe(attributes),
        start_time=activities[0]['timestamp'],
        end_time=activities[-1]['timestamp'],
    )


def _json_safe(value):
    """
    Make a value storable in a JSON column.

    PostgreSQL rejects the non-standard ``NaN`` and ``Infinity`` literals
    that Python's ``json`` module writes for those floats, and an event log
    does contain them — a resource that was never assigned is read as NaN
    by the XES reader.
    """
    import math

    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, str) or value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    # numpy scalars and pandas timestamps
    try:
        import numpy as np
        if isinstance(value, np.generic):
            return _json_safe(value.item())
    except ImportError:
        pass
    try:
        import pandas as pd
        if isinstance(value, (pd.Timestamp,)):
            return value.isoformat()
    except (ImportError, TypeError):
        pass
    return str(value)


def _scalar(value):
    """Convert a numpy/pandas scalar into a plain Python value."""
    try:
        import numpy as np
        if isinstance(value, np.generic):
            value = value.item()
    except ImportError:
        pass
    if isinstance(value, float) and value != value:  # NaN
        return None
    return value


def _iso(value) -> str:
    """Render a timestamp as an ISO-8601 string, empty when absent."""
    if value is None:
        return ''
    try:
        import pandas as pd
        if pd.isna(value):
            return ''
    except (TypeError, ValueError):
        pass
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


def split_cases(cases: dict, spec: LogSpec):
    """
    Split cases by time into a training and a test part.

    The cutoff is the ``split_ratio`` quantile of the case start times, so
    the split follows the chronology of the log rather than an arbitrary
    case ordering.  Cases that share the exact cutoff timestamp all land on
    the same side, which keeps the split free of leakage.
    """
    if not cases:
        return {}, {}

    import pandas as pd

    starts = pd.to_datetime([c.start_time for c in cases.values()],
                             utc=True, errors='coerce')
    valid = starts.dropna()
    if valid.empty:
        return dict(cases), {}

    cutoff = pd.Series(valid).quantile(spec.split_ratio)

    train, test = {}, {}
    for case, start in zip(cases.values(), starts):
        if pd.isna(start) or start <= cutoff:
            case.split = 'train'
            train[case.case_id] = case
        else:
            case.split = 'test'
            test[case.case_id] = case
    return train, test


def import_log(dataset_key: str, process_id=None, split_ratio: float | None = None,
               max_cases: int | None = None, persist: bool = True,
               replace: bool = True):
    """
    Import a supported event log into the database.

    Creates (or reuses) the ``EventLog`` row and one ``Case`` row per
    process instance, tagged with its train/test split.

    :param replace: delete the cases already stored for this event log
        before importing.  Re-importing without it would create duplicates.
    :returns: a dict with the import statistics.
    """
    from apps.benchmark.models import Case, EventLog

    if dataset_key not in SUPPORTED_LOGS:
        raise KeyError(f'Unsupported dataset "{dataset_key}". '
                       f'Known datasets: {sorted(SUPPORTED_LOGS)}')

    spec = SUPPORTED_LOGS[dataset_key]
    if split_ratio is not None:
        spec = LogSpec(**{**spec.__dict__, 'split_ratio': split_ratio})

    path = log_path(dataset_key)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f'Event log "{dataset_key}" not found at {path}. '
            f'Run scripts/fetch_event_logs.ps1 to download the public logs.'
        )

    log.info('Reading %s from %s', dataset_key, path)
    if os.path.getsize(path) > STREAM_THRESHOLD_BYTES:
        cases = stream_xes_cases(path, spec)
    else:
        df = read_xes_frame(path)
        df = _normalise_frame(df, spec)
        cases = extract_cases(df, spec)
    train, test = split_cases(cases, spec)

    activities = sorted({a['activity'] for c in cases.values()
                         for a in c.activities})
    num_events = sum(len(c.activities) for c in cases.values())

    if persist:
        event_log, _ = EventLog.objects.update_or_create(
            name=spec.key,
            defaults={
                'display_name': spec.display_name,
                'description':  spec.description,
                'num_traces':   len(cases),
                'num_events':   num_events,
                'activities':   activities,
                'metadata': {
                    'domain':       spec.domain,
                    'source_file':  spec.filename,
                    'split_ratio':  spec.split_ratio,
                    'train_cases':  len(train),
                    'test_cases':   len(test),
                    'cutoff':       _iso(pd_cutoff(cases, spec)),
                },
            },
        )

        if replace:
            deleted, _ = Case.objects.filter(event_log=event_log).delete()
            log.info('Removed %s previously imported cases of %s.',
                     deleted, spec.key)

        _persist_cases(event_log, cases, spec, max_cases)
    else:
        event_log = None

    return {
        'dataset':       spec.key,
        'event_log_id':  str(event_log.id) if event_log else None,
        'num_cases':     len(cases),
        'num_events':    num_events,
        'num_activities': len(activities),
        'train_cases':   len(train),
        'test_cases':    len(test),
        'activities':    activities,
    }


def _has_pandas() -> bool:
    try:
        import pandas  # noqa: F401
        return True
    except ImportError:
        return False


def pd_cutoff(cases, spec):
    import pandas as pd
    starts = pd.to_datetime([c.start_time for c in cases.values()],
                             utc=True, errors='coerce')
    valid = starts.dropna()
    return pd.Series(valid).quantile(spec.split_ratio) if not valid.empty else pd.NaT


def _persist_cases(event_log, cases, spec, max_cases):
    """
    Bulk-create the ``Case`` rows for the imported traces.

    A case holds the *complete* observed trace of the log, so that the raw
    event data stays faithful to the source.  The split into an executed
    prefix and a continuation happens when the benchmark scenarios are
    built, because that is where the perturbation is injected.
    """
    from apps.benchmark.models import Case

    rows = []
    for case in cases.values():
        attributes = dict(case.attributes or {})
        attributes['split'] = case.split
        attributes['trace_length'] = len(case.activities)
        rows.append(Case(
            event_log=event_log,
            case_id=case.case_id,
            prefix_trace=case.activities,
            attributes=attributes,
            current_stage=case.activities[-1]['activity'] if case.activities else '',
        ))
        if max_cases and len(rows) >= max_cases:
            break

    Case.objects.bulk_create(rows, batch_size=500)
    return len(rows)


def split_prefix(events: list, spec: LogSpec, ratio: float = 0.6,
                 min_continuation: int = 2):
    """
    Split an observed trace into an executed prefix and its continuation.

    The cut is placed at a decision activity near the ``ratio`` mark of the
    trace, so that the agent faces a real decision rather than the
    bookkeeping at the end of the case.  The cut always leaves at least
    ``min_continuation`` events in the continuation: a continuation of one
    event cannot carry a decision, and the reference behaviour of such a
    case would be mostly the bookkeeping of the frame.

    :returns: ``(prefix, continuation)`` — two lists of event dicts.
    """
    events = [event for event in (events or []) if event.get('activity')]
    if len(events) < 3:
        return events, []

    target = max(1, min(len(events) - 1, int(len(events) * ratio)))
    # Leave a continuation that can carry a decision.
    target = min(target, max(1, len(events) - min_continuation))

    decisions = set(spec.decision_activities)
    cut = None
    for index, event in enumerate(events):
        if index + 1 > target:
            break
        if event.get('activity') in decisions and abs(index - target) <= 2:
            if len(events) - (index + 1) >= min_continuation:
                cut = index + 1
                break
    if cut is None:
        cut = target

    return events[:cut], events[cut:]


def build_alternative_index(cases) -> dict:
    """
    Index the continuations that the log observed for every prefix.

    The index maps a prefix — the tuple of activities executed so far — to
    the continuations that were really recorded after it.  It is the
    evidence base of the WF-Adapt exception scenario: the compliant
    alternative path of a case is not invented, it is the path the same
    process actually took in the other cases that reached the same state.

    Only the training split is indexed, so that the test cases never
    contribute to the reference behaviour of another test case.

    :param cases: an iterable of ``Case`` rows of the training split
    :returns: ``{prefix tuple: {continuation tuple: count}}``
    """
    index: dict[tuple, dict[tuple, int]] = {}

    for case in cases:
        activities = [event.get('activity', '')
                      for event in (case.prefix_trace or []) if event.get('activity')]
        for cut in range(1, len(activities)):
            prefix = tuple(activities[:cut])
            continuation = tuple(activities[cut:])
            if not continuation:
                continue
            bucket = index.setdefault(prefix, {})
            bucket[continuation] = bucket.get(continuation, 0) + 1

    return index


def alternative_continuation(index: dict, prefix: list, observed: list):
    """
    The compliant alternative path for a prefix.

    :param index:    the index built by :func:`build_alternative_index`
    :param prefix:   the executed prefix of the case
    :param observed: the continuation the case itself took
    :returns: ``(activities, count)`` of the most frequent *other*
              continuation, or ``(None, 0)`` when the log shows no
              alternative for this prefix.
    """
    key = tuple(activity for activity in (prefix or []) if activity)
    bucket = index.get(key)
    if not bucket:
        return None, 0

    observed_tuple = tuple(observed or [])
    candidates = [(count, continuation)
                  for continuation, count in bucket.items()
                  if continuation != observed_tuple]
    if not candidates:
        return None, 0

    # Most frequent alternative; ties are broken by the shorter path, so
    # that the reference behaviour is the least intrusive one.
    candidates.sort(key=lambda item: (-item[0], len(item[1])))
    count, continuation = candidates[0]
    return list(continuation), count

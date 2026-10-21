"""CARMA — Benchmark Celery tasks (XES log import)."""
import logging
import os
import tempfile

from celery import shared_task
from django.core.files.storage import default_storage
from django.utils import timezone

log = logging.getLogger('carma')

# Guard against importing an unbounded log into the database.
MAX_CASES_PER_IMPORT = 5000


@shared_task(bind=True, max_retries=1, default_retry_delay=30)
def import_event_log(self, log_name: str, file_path: str = None,
                     storage_path: str = None):
    """
    Import a BPI XES event log and persist its traces as ``Case`` rows.

    :param log_name:     key of the event log (``bpi2017``, ``bpi2019``, ...)
    :param file_path:    absolute path of an XES file on the worker filesystem
    :param storage_path: path of a file already saved in the Django storage
                         (used when the file was uploaded through the API)
    """
    import pm4py

    from apps.benchmark.models import Case, EventLog

    source_path = file_path
    temp_file = None
    try:
        if source_path is None and storage_path:
            with default_storage.open(storage_path, 'rb') as handle:
                suffix = os.path.splitext(storage_path)[1] or '.xes'
                handle.seek(0)
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(handle.read())
                    source_path = tmp.name
                    temp_file = tmp.name

        if not source_path:
            log.warning('No XES file supplied for "%s".', log_name)
            return {'status': 'skipped', 'reason': 'No XES file supplied.'}

        event_log_obj, _ = EventLog.objects.get_or_create(
            name=log_name,
            defaults={'display_name': log_name.upper(), 'imported_at': timezone.now()},
        )

        xes_log = pm4py.read_xes(source_path)

        cases_created = 0
        activities: set[str] = set()
        num_events = 0
        for trace in xes_log:
            if cases_created >= MAX_CASES_PER_IMPORT:
                log.warning('Import truncated at %d cases.', MAX_CASES_PER_IMPORT)
                break
            case_id = trace.attributes.get('concept:name', f'case_{cases_created}')
            prefix = []
            for event in trace:
                activity = event.get('concept:name', '')
                activities.add(activity)
                num_events += 1
                prefix.append({
                    'activity':  activity,
                    'timestamp': str(event.get('time:timestamp', '')),
                    'attributes': {k: str(v) for k, v in event.items()
                                   if k not in ('concept:name', 'time:timestamp')},
                })
            Case.objects.update_or_create(
                event_log=event_log_obj, case_id=str(case_id),
                defaults={'prefix_trace': prefix, 'attributes': dict(trace.attributes)},
            )
            cases_created += 1

        event_log_obj.num_traces = cases_created
        event_log_obj.num_events = num_events
        event_log_obj.activities = sorted(activities)
        event_log_obj.imported_at = timezone.now()
        event_log_obj.save(update_fields=['num_traces', 'num_events', 'activities', 'imported_at'])

        log.info('Imported %d cases (%d events) from %s.', cases_created, num_events, log_name)
        return {'status': 'done', 'cases_imported': cases_created, 'events_imported': num_events}

    except Exception as exc:
        log.exception('import_event_log failed: %s', exc)
        raise self.retry(exc=exc)
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError:
                pass

"""CARMA — Benchmark Celery tasks (XES log import)."""
import logging
from celery import shared_task

log = logging.getLogger('carma')


@shared_task(bind=True, max_retries=1)
def import_event_log(self, log_name: str, file_path: str = None):
    """
    Import a BPI XES event log, extract traces, persist Cases.
    Uses PM4Py for XES parsing.
    """
    try:
        import pm4py
        from apps.benchmark.models import EventLog, Case

        event_log_obj, _ = EventLog.objects.get_or_create(
            name=log_name,
            defaults={'display_name': log_name.upper()}
        )

        if file_path:
            log_pm4 = pm4py.read_xes(file_path)
        else:
            # Load bundled sample if no file provided
            log.warning('No file provided for %s — using sample stub.', log_name)
            return {'status': 'skipped', 'reason': 'No file provided.'}

        cases_created = 0
        for trace in log_pm4:
            case_id = trace.attributes.get('concept:name', f'case_{cases_created}')
            prefix  = [
                {
                    'activity':  e.get('concept:name', ''),
                    'timestamp': str(e.get('time:timestamp', '')),
                    'attributes': {k: str(v) for k, v in e.items()
                                   if k not in ('concept:name', 'time:timestamp')},
                }
                for e in trace
            ]
            Case.objects.update_or_create(
                event_log=event_log_obj, case_id=case_id,
                defaults={'prefix_trace': prefix, 'attributes': dict(trace.attributes)}
            )
            cases_created += 1

        event_log_obj.num_traces = cases_created
        event_log_obj.save(update_fields=['num_traces'])

        log.info('Imported %d cases from %s.', cases_created, log_name)
        return {'status': 'done', 'cases_imported': cases_created}

    except Exception as exc:
        log.exception('import_event_log failed: %s', exc)
        raise self.retry(exc=exc)

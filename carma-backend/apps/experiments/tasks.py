"""
CARMA — Celery Tasks: Experiment Orchestration
Runs the full B0-B7 experiment pipeline on WF-Adapt benchmark cases.
"""
import logging
import time

from celery import group, shared_task
from django.db.models import Avg, Case, Count, FloatField, Q, Sum, Value, When
from django.utils import timezone

log = logging.getLogger('carma')

# Adaptations whose executed trace violates a hard constraint.  Rows recorded
# before ``hard_violation`` existed fall back to "any violation cost".
HARD_VIOLATION = Q(hard_violation=True) | Q(hard_violation__isnull=True, viol_cost__gt=0)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def run_experiment(self, run_id: str):
    """
    Master task: fan out all benchmark cases of a run.

    Uses a Celery chord: ``group(run_case.s(...)) | aggregate_results.s(run_id)``.
    """
    from apps.benchmark.models import BenchmarkCase
    from apps.experiments.models import ExperimentRun
    from carma_engine.llm.client import LLMUnavailable
    from carma_engine.runners import get_runner

    try:
        run = ExperimentRun.objects.select_related(
            'configuration', 'constraint_set', 'process').get(id=run_id)
    except ExperimentRun.DoesNotExist:
        log.error('ExperimentRun %s not found.', run_id)
        return {'status': 'failed', 'error': 'run not found'}

    # A configuration whose model cannot be reached would fail every case;
    # the run stops here instead of recording hundreds of failures.
    try:
        get_runner(run.configuration.code, config=run.configuration, seed=run.seed).check_llm()
    except LLMUnavailable as exc:
        run.status = 'failed'
        run.error_log = str(exc)
        run.save(update_fields=['status', 'error_log'])
        _push_progress(run_id, 0, 0, 'failed')
        log.error('Experiment %s not started: %s', run_id, exc)
        return {'status': 'failed', 'error': str(exc)}

    run.status    = 'running'
    run.started_at = timezone.now()

    cases = BenchmarkCase.objects.filter(
        process=run.process, is_validated=True
    ).select_related('case', 'scenario', 'constraint_set')

    run.total_cases = cases.count()
    run.save(update_fields=['status', 'started_at', 'total_cases'])

    _push_progress(run_id, run.total_cases, 0, 'running')

    if not run.total_cases:
        # Nothing to do — finalise immediately so the run does not stay
        # "running" forever.
        aggregate_results.apply(args=[[], run_id])
        return {'status': 'completed', 'cases': 0}

    subtasks = group(run_case.s(run_id, str(bc.id)) for bc in cases)
    callback = aggregate_results.s(run_id)
    chord = subtasks | callback
    chord.apply_async()
    log.info('Experiment %s: dispatched %d case tasks.', run_id, run.total_cases)
    return {'status': 'running', 'cases': run.total_cases}


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def run_case(self, run_id: str, benchmark_case_id: str):
    """
    Run the CARMA pipeline for a single benchmark case.

    :returns: a small summary dict (the full result is persisted as an
              ``Adaptation``).
    """
    from apps.experiments.models import ExperimentRun

    start = time.monotonic()

    try:
        run = ExperimentRun.objects.select_related('configuration').get(id=run_id)
        from apps.benchmark.models import BenchmarkCase
        bc = BenchmarkCase.objects.select_related(
            'case', 'scenario', 'process', 'constraint_set').get(id=benchmark_case_id)
    except Exception as exc:
        log.exception('run_case setup error: %s', exc)
        return {'status': 'failed', 'error': str(exc)}

    from carma_engine.runners import get_runner

    try:
        runner = get_runner(run.configuration.code, config=run.configuration, seed=run.seed)
        output = runner.run(bc, run.configuration)
    except Exception as exc:
        log.exception('run_case failed for bc=%s: %s', benchmark_case_id, exc)
        _increment(run, 'failed_cases')
        return {'status': 'failed', 'error': str(exc)}

    output['latency_s'] = output.get('latency_s') or (time.monotonic() - start)

    try:
        adaptation = persist_outcome(run, bc, output)
    except Exception as exc:
        log.exception('Could not persist adaptation for bc=%s: %s', benchmark_case_id, exc)
        _increment(run, 'failed_cases')
        return {'status': 'failed', 'error': str(exc)}

    _increment(run, 'failed_cases' if adaptation.status == 'failed' else 'completed_cases')
    _push_progress(run_id, run.total_cases, run.completed_cases, 'running')
    return {'adaptation_id': str(adaptation.id), 'status': adaptation.status}


def persist_outcome(run, benchmark_case, output: dict):
    """
    Store the outcome of one case: the adaptation, its hash-chained audit
    entries and, when the case was escalated, its review-queue entry.

    Both execution paths — this Celery task and ``manage.py run_experiment`` —
    go through here, so they record identical rows.
    """
    from apps.experiments.models import Adaptation

    viol_cost = float(output.get('viol_cost') or 0.0)
    exec_cost = float(output.get('exec_cost') or 0.0)
    adaptation = Adaptation.objects.create(
        run                  = run,
        benchmark_case       = benchmark_case,
        plan_id              = output.get('plan_id', ''),
        adaptation           = output.get('plan') or {},
        activity_seq         = output.get('activity_seq') or [],
        planned_seq          = output.get('planned_seq') or [],
        confidence           = output.get('confidence'),
        scv_approved         = output.get('scv_approved'),
        scv_token            = output.get('scv_token') or '',
        viol_cost            = viol_cost,
        exec_cost            = exec_cost,
        total_cost           = viol_cost + exec_cost,
        retrieved_docs       = output.get('retrieved_docs') or [],
        retrieval_scores     = output.get('retrieval_scores') or {},
        task_success         = output.get('task_success'),
        goal_reached         = output.get('goal_reached'),
        gold_exact_match     = output.get('gold_exact_match'),
        gold_similarity      = output.get('gold_similarity'),
        hard_violation       = output.get('hard_violation'),
        unsafe_action        = output.get('unsafe_action'),
        conformance_fitness  = output.get('conformance_fitness'),
        repair_rounds        = int(output.get('repair_rounds') or 0),
        plan_source          = output.get('plan_source') or '',
        llm_backend          = output.get('llm_backend') or '',
        served_by            = output.get('served_by') or {},
        llm_calls            = int(output.get('llm_calls') or 0),
        usd_cost             = output.get('usd_cost'),
        error                = output.get('error') or '',
        status               = output.get('status') or 'failed',
        latency_s            = output.get('latency_s'),
        llm_tokens           = int(output.get('tokens_used') or 0),
    )
    _write_audit(run, benchmark_case, adaptation, output)
    if output.get('needs_escalation'):
        _create_escalation(adaptation, output)
    _push(run.id, {
        'type':           'case_complete',
        'adaptation_id':  str(adaptation.id),
        'case_id':        benchmark_case.case.case_id,
        'scenario':       benchmark_case.scenario.code,
        'status':         adaptation.status,
        'task_success':   adaptation.task_success,
        'hard_violation': adaptation.hard_violation,
        'latency_s':      adaptation.latency_s,
        'ts':             timezone.now().isoformat(),
    })
    return adaptation


@shared_task
def aggregate_results(results, run_id: str):
    """Chord callback — aggregate metrics after all cases have completed."""
    from apps.experiments.models import Adaptation, ExperimentRun, RunResult

    try:
        run = ExperimentRun.objects.get(id=run_id)
        adaptations = Adaptation.objects.filter(run=run)

        # PostgreSQL cannot cast boolean to a numeric type, so the boolean
        # outcome is mapped to 1.0/0.0 explicitly.  AVG() ignores the NULL
        # default, so adaptations without a recorded outcome are excluded
        # from both the numerator and the denominator.
        task_success_rate = Case(
            When(task_success=True, then=Value(1.0)),
            When(task_success=False, then=Value(0.0)),
            default=Value(None),
            output_field=FloatField(),
        )

        aggs = adaptations.aggregate(
            mean_tsr     = Avg(task_success_rate),
            mean_fitness = Avg('conformance_fitness'),
            mean_lat     = Avg('latency_s'),
            mean_exec    = Avg('exec_cost'),
            mean_viol    = Avg('viol_cost'),
            total_tokens = Sum('llm_tokens'),
            n            = Count('id'),
            n_violations = Count('id', filter=HARD_VIOLATION),
            n_escalated  = Count('id', filter=Q(status='escalated')),
            n_success    = Count('id', filter=Q(status='success')),
        )

        total = aggs['n'] or 0
        # Constraint Violation Rate = share of adaptations whose executed
        # trace violates at least one hard constraint (not the mean cost).
        cvr = (aggs['n_violations'] / total) if total else None
        escalation_rate = (aggs['n_escalated'] / total) if total else None
        repair_rate = (aggs['n_success'] / total) if total else None

        latencies = [value for value in adaptations.values_list('latency_s', flat=True)
                     if value is not None]
        p95 = float(_percentile(latencies, 95)) if latencies else None

        RunResult.objects.update_or_create(
            run=run,
            defaults={
                'task_success_rate':    aggs['mean_tsr'],
                'constraint_viol_rate': cvr,
                'conformance_fitness':  aggs['mean_fitness'],
                'escalation_rate':      escalation_rate,
                'repair_rate':          repair_rate,
                'mean_latency_s':       aggs['mean_lat'],
                'p95_latency_s':        p95,
                'mean_viol_cost':       aggs['mean_viol'],
                'mean_exec_cost':       aggs['mean_exec'],
                'total_llm_tokens':     aggs['total_tokens'] or 0,
            },
        )

        _write_run_metrics(run)

        run.status       = 'completed'
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'completed_at'])

        _push_progress(run_id, run.total_cases, run.completed_cases, 'completed')
        log.info('Experiment %s completed. TSR=%s', run_id, aggs.get('mean_tsr'))
    except Exception as exc:
        log.exception('aggregate_results failed for run=%s: %s', run_id, exc)
        ExperimentRun.objects.filter(id=run_id).update(
            status='failed', error_log=str(exc))


# ── Helpers ────────────────────────────────────────────────────
def _increment(run, field: str):
    """Atomically increment a counter on the run."""
    from django.db.models import F

    from apps.experiments.models import ExperimentRun

    ExperimentRun.objects.filter(id=run.id).update(**{field: F(field) + 1})
    run.refresh_from_db(fields=[field])


def _percentile(values: list, percentile: float) -> float:
    """Linear-interpolation percentile (numpy-free)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * (percentile / 100.0)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def _write_run_metrics(run):
    """Persist the per-scenario metric snapshots used by the metrics screens."""
    from apps.experiments.models import Adaptation
    from apps.metrics.models import RunMetrics

    adaptations = Adaptation.objects.filter(run=run).select_related('benchmark_case')
    rows = {}

    def _blank():
        return {'tsr': None, 'cvr': None, 'conformance': None,
                'escalation_rate': None, 'mean_latency': None,
                'p95_latency': None, 'n': 0, 'n_viol': 0, 'n_esc': 0}

    for scenario_code in [''] + sorted(
            {a.benchmark_case.scenario.code for a in adaptations}):
        bucket = _blank()
        latencies = []
        for adaptation in adaptations:
            if scenario_code and adaptation.benchmark_case.scenario.code != scenario_code:
                continue
            bucket['n'] += 1
            if adaptation.task_success is not None:
                bucket['tsr'] = (bucket['tsr'] or 0) + (1.0 if adaptation.task_success else 0.0)
            if adaptation.constraint_violated:
                bucket['n_viol'] += 1
            if adaptation.status == 'escalated':
                bucket['n_esc'] += 1
            if adaptation.conformance_fitness is not None:
                bucket['conformance'] = (bucket['conformance'] or 0) + adaptation.conformance_fitness
            if adaptation.latency_s is not None:
                latencies.append(adaptation.latency_s)
        if not bucket['n']:
            continue
        RunMetrics.objects.update_or_create(
            run=run, scenario_code=scenario_code,
            defaults={
                'tsr': (bucket['tsr'] or 0) / bucket['n'],
                'cvr': bucket['n_viol'] / bucket['n'],
                'conformance': (bucket['conformance'] or 0) / bucket['n'],
                'escalation_rate': bucket['n_esc'] / bucket['n'],
                'mean_latency': (sum(latencies) / len(latencies)) if latencies else None,
                'p95_latency': _percentile(latencies, 95) if latencies else None,
            },
        )
        rows[scenario_code] = bucket


def _push_progress(run_id, total, completed, status):
    """Push real-time progress to the WebSocket channel group."""
    _push(run_id, {
        'type':      'progress',
        'run_id':    str(run_id),
        'total':     total,
        'completed': completed,
        'pct':       round(completed / total * 100, 1) if total else 0,
        'status':    status,
        'ts':        timezone.now().isoformat(),
    })


def _push(run_id, data: dict):
    """Send one message to the run's live stream (``ws/experiments/<id>/logs/``)."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        async_to_sync(get_channel_layer().group_send)(
            f'run_{run_id}', {'type': 'experiment_log', 'data': data})
    except Exception as exc:
        log.debug('WebSocket push failed: %s', exc)


def _write_audit(run, benchmark_case, adaptation, output):
    """Append the hash-chained audit entries for one completed adaptation."""
    from apps.audit.services import append_audit_entry

    run_id = run.id
    case_id = benchmark_case.case.case_id

    entries = [
        ('retrieval', {
            'documents': output.get('retrieved_docs') or [],
            'scores': output.get('retrieval_scores') or {},
        }, 'retriever'),
        ('plan', {
            'plan_id': adaptation.plan_id,
            'plan': adaptation.adaptation,
            'planned_seq': adaptation.planned_seq,
            'plan_source': adaptation.plan_source,
            'confidence': adaptation.confidence,
        }, 'planner'),
        ('scv_check', {
            'approved': adaptation.scv_approved,
            'token': adaptation.scv_token,
            'violation_report': output.get('violation_report') or {},
        }, 'scv'),
        ('action', {
            'status': adaptation.status,
            'executed_seq': adaptation.activity_seq,
            'viol_cost': adaptation.viol_cost,
            'exec_cost': adaptation.exec_cost,
            'total_cost': adaptation.total_cost,
            'latency_s': adaptation.latency_s,
            'repair_rounds': adaptation.repair_rounds,
            'error': adaptation.error,
        }, 'executor'),
    ]

    for entry_type, payload, actor in entries:
        try:
            append_audit_entry(
                entry_type=entry_type,
                payload=payload,
                run_id=run_id,
                adaptation_id=adaptation.id,
                case_id=case_id,
                actor_agent=actor,
            )
        except Exception as exc:
            log.warning('Audit write failed (%s): %s', entry_type, exc)


def _create_escalation(adaptation, output):
    """Create the review-queue entry of an escalated case."""
    try:
        from apps.reviews.models import Escalation

        detail = output.get('escalation_reason') or ''
        if adaptation.scv_approved is False:
            reason = 'scv_violation'
        elif 'declined' in detail:
            reason = 'declined'
        elif 'Repair budget' in detail:
            reason = 'repair_exhausted'
        elif 'confidence' in detail:
            reason = 'low_confidence'
        else:
            reason = 'policy_breach'

        # Nothing ran, so the cost the reviewer needs is that of the plan
        # the verifier saw.
        proposed_cost = float((output.get('violation_report') or {}).get('total_cost') or 0.0)
        Escalation.objects.get_or_create(
            adaptation=adaptation,
            defaults={
                'reason':       reason,
                'reason_detail': detail,
                'confidence':   output.get('confidence'),
                'viol_cost':    proposed_cost,
                'priority':     1 if proposed_cost > 5 else 2,
            }
        )
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            async_to_sync(get_channel_layer().group_send)(
                'review_queue',
                {'type': 'review_notification', 'data': {
                    'type':          'new_escalation',
                    'adaptation_id': str(adaptation.id),
                    'reason':        reason,
                }}
            )
        except Exception:
            pass
    except Exception as exc:
        log.warning('Escalation create failed: %s', exc)

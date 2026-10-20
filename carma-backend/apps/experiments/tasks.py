"""
CARMA — Celery Tasks: Experiment Orchestration
Runs the full B0-B7 experiment pipeline on WF-Adapt benchmark cases.
"""
import logging
from celery import shared_task, chord, group
from django.utils import timezone

log = logging.getLogger('carma')


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def run_experiment(self, run_id: str):
    """
    Master task: fan-out all benchmark cases for the given run.
    Uses a Celery chord: group(run_case.s(...)) | aggregate_results.s(run_id)
    """
    from apps.experiments.models import ExperimentRun
    from apps.benchmark.models import BenchmarkCase

    try:
        run = ExperimentRun.objects.select_related(
            'configuration', 'constraint_set', 'process').get(id=run_id)
    except ExperimentRun.DoesNotExist:
        log.error('ExperimentRun %s not found.', run_id)
        return

    run.status    = 'running'
    run.started_at = timezone.now()

    # Get all validated benchmark cases for this process
    cases = BenchmarkCase.objects.filter(
        process=run.process, is_validated=True
    ).select_related('case', 'scenario', 'constraint_set')

    run.total_cases = cases.count()
    run.save(update_fields=['status', 'started_at', 'total_cases'])

    # Broadcast via WebSocket
    _push_progress(run_id, run.total_cases, 0, 'running')

    # Build chord: parallel case runs → aggregate
    subtasks = group(
        run_case.s(run_id, str(bc.id))
        for bc in cases
    )
    callback = aggregate_results.s(run_id)
    chord(subtasks)(callback)
    log.info('Experiment %s: dispatched %d case tasks.', run_id, run.total_cases)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def run_case(self, run_id: str, benchmark_case_id: str):
    """
    Run CARMA pipeline for a single benchmark case.
    Returns adaptation result dict.
    """
    from apps.experiments.models import ExperimentRun, Adaptation
    from apps.benchmark.models import BenchmarkCase
    import time

    start = time.monotonic()

    try:
        run = ExperimentRun.objects.select_related('configuration').get(id=run_id)
        bc  = BenchmarkCase.objects.select_related(
            'case', 'scenario', 'process', 'constraint_set').get(id=benchmark_case_id)
    except Exception as exc:
        log.exception('run_case setup error: %s', exc)
        return {'status': 'failed', 'error': str(exc)}

    config = run.configuration

    try:
        # ── 1. State Estimator ──
        prefix     = bc.case.prefix_trace
        current_stage = bc.case.current_stage

        # ── 2. CAR Retrieval (if enabled) ──
        retrieved_docs = []
        retrieval_scores = {}
        if config.use_car:
            from apps.engine.car_retriever import CARRetriever
            retriever = CARRetriever(
                process_id=str(bc.process_id),
                top_k=config.top_k,
                alpha=config.alpha,
                beta=config.beta,
                gamma=config.gamma,
            )
            retrieved_docs, retrieval_scores = retriever.retrieve(
                prefix=prefix,
                stage=current_stage,
                perturbation=bc.perturbation,
            )
        else:
            # Plain vector RAG (B2/B4)
            from apps.engine.car_retriever import plain_vector_rag
            retrieved_docs = plain_vector_rag(str(bc.process_id), bc.perturbation_text)

        # ── 3. LangGraph Agents ──
        if config.multi_agent:
            from apps.engine.agents import run_multi_agent
            result = run_multi_agent(
                config=config, prefix=prefix, perturbation=bc.perturbation,
                retrieved_docs=retrieved_docs, constraint_set=bc.constraint_set,
                use_scv=config.use_scv,
            )
        else:
            from apps.engine.agents import run_single_llm
            result = run_single_llm(
                config=config, prefix=prefix, perturbation=bc.perturbation,
                retrieved_docs=retrieved_docs,
            )

        # ── 4. SCV Verification (if enabled) ──
        scv_approved, scv_token, viol_cost = None, '', 0.0
        if config.use_scv and result.get('plan'):
            from apps.engine.scv_verifier import SCVVerifier
            verifier = SCVVerifier(constraint_set=bc.constraint_set)
            scv_approved, scv_token, viol_cost = verifier.verify(
                plan=result['plan'],
                prefix=prefix,
                process=bc.process,
            )

        latency = time.monotonic() - start

        # ── 5. Persist Adaptation ──
        adaptation = Adaptation.objects.create(
            run              = run,
            benchmark_case   = bc,
            plan_id          = result.get('plan_id', ''),
            adaptation       = result.get('plan', {}),
            activity_seq     = result.get('activity_seq', []),
            confidence       = result.get('confidence'),
            scv_approved     = scv_approved,
            scv_token        = scv_token or '',
            viol_cost        = viol_cost,
            exec_cost        = result.get('exec_cost', 0.0),
            total_cost       = viol_cost + result.get('exec_cost', 0.0),
            retrieved_docs   = retrieved_docs,
            retrieval_scores = retrieval_scores,
            task_success     = result.get('task_success'),
            conformance_fitness = result.get('conformance_fitness'),
            repair_rounds    = result.get('repair_rounds', 0),
            status           = result.get('status', 'success'),
            latency_s        = latency,
            llm_tokens       = result.get('tokens_used', 0),
        )

        # ── 6. Audit log entry ──
        _write_audit(run_id, adaptation)

        # ── 7. Progress update ──
        run.completed_cases += 1
        run.save(update_fields=['completed_cases'])
        _push_progress(run_id, run.total_cases, run.completed_cases, 'running')

        # ── 8. Escalation if needed ──
        if result.get('needs_escalation'):
            _create_escalation(adaptation, result)

        return {'adaptation_id': str(adaptation.id), 'status': adaptation.status}

    except Exception as exc:
        log.exception('run_case failed for bc=%s: %s', benchmark_case_id, exc)
        run.failed_cases += 1
        run.save(update_fields=['failed_cases'])
        return {'status': 'failed', 'error': str(exc)}


@shared_task
def aggregate_results(results, run_id: str):
    """Chord callback — aggregate metrics after all cases complete."""
    from apps.experiments.models import ExperimentRun, Adaptation, RunResult
    from django.db.models import Avg, Count, Q
    import numpy as np

    try:
        run = ExperimentRun.objects.get(id=run_id)
        adaptations = Adaptation.objects.filter(run=run)

        aggs = adaptations.aggregate(
            mean_tsr   = Avg('task_success'),
            mean_cvr   = Avg('viol_cost'),
            mean_fitness = Avg('conformance_fitness'),
            mean_lat   = Avg('latency_s'),
            mean_exec  = Avg('exec_cost'),
            mean_viol  = Avg('viol_cost'),
            total_tokens = Count('llm_tokens'),
        )

        latencies = list(adaptations.values_list('latency_s', flat=True))
        p95 = float(np.percentile(latencies, 95)) if latencies else None

        RunResult.objects.update_or_create(
            run=run,
            defaults={
                'task_success_rate':    aggs['mean_tsr'],
                'constraint_viol_rate': aggs['mean_cvr'],
                'conformance_fitness':  aggs['mean_fitness'],
                'mean_latency_s':       aggs['mean_lat'],
                'p95_latency_s':        p95,
                'mean_viol_cost':       aggs['mean_viol'],
                'mean_exec_cost':       aggs['mean_exec'],
                'total_llm_tokens':     aggs['total_tokens'] or 0,
            }
        )

        run.status       = 'completed'
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'completed_at'])

        _push_progress(run_id, run.total_cases, run.completed_cases, 'completed')
        log.info('Experiment %s completed. TSR=%.3f', run_id, aggs.get('mean_tsr') or 0)

    except Exception as exc:
        log.exception('aggregate_results failed for run=%s: %s', run_id, exc)
        ExperimentRun.objects.filter(id=run_id).update(
            status='failed', error_log=str(exc))


# ── Helpers ────────────────────────────────────────────────────
def _push_progress(run_id, total, completed, status):
    """Push real-time progress to WebSocket channel group."""
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(
            f'run_{run_id}',
            {
                'type': 'experiment_log',
                'data': {
                    'type':      'progress',
                    'run_id':    run_id,
                    'total':     total,
                    'completed': completed,
                    'pct':       round(completed / total * 100, 1) if total else 0,
                    'status':    status,
                    'ts':        timezone.now().isoformat(),
                }
            }
        )
    except Exception as e:
        log.debug('WebSocket push failed: %s', e)


def _write_audit(run_id, adaptation):
    """Append a hash-chained audit entry for the completed adaptation."""
    try:
        from apps.audit.models import AuditLogEntry
        last = AuditLogEntry.objects.filter(run_id=run_id).order_by('-sequence_num').first()
        seq  = (last.sequence_num + 1) if last else 1
        prev = last.entry_hash if last else '0' * 64

        AuditLogEntry.objects.create(
            sequence_num  = seq,
            prev_hash     = prev,
            entry_type    = 'action',
            run_id        = run_id,
            adaptation_id = adaptation.id,
            case_id       = adaptation.benchmark_case.case.case_id,
            actor_agent   = 'executor',
            payload       = {
                'status':     adaptation.status,
                'viol_cost':  adaptation.viol_cost,
                'exec_cost':  adaptation.exec_cost,
                'latency_s':  adaptation.latency_s,
                'scv_token':  adaptation.scv_token,
            },
        )
    except Exception as e:
        log.warning('Audit write failed: %s', e)


def _create_escalation(adaptation, result):
    """Create an escalation record for low-confidence or violation cases."""
    try:
        from apps.reviews.models import Escalation
        reason = 'low_confidence' if result.get('confidence', 1) < 0.5 else 'scv_violation'
        Escalation.objects.get_or_create(
            adaptation=adaptation,
            defaults={
                'reason':       reason,
                'reason_detail': result.get('escalation_reason', ''),
                'confidence':   result.get('confidence'),
                'viol_cost':    adaptation.viol_cost,
                'priority':     1 if adaptation.viol_cost > 5 else 2,
            }
        )
        # Notify review queue via WebSocket
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            async_to_sync(get_channel_layer().group_send)(
                'review_queue',
                {'type': 'review_notification', 'data': {
                    'type':         'new_escalation',
                    'adaptation_id': str(adaptation.id),
                    'reason':       reason,
                }}
            )
        except Exception:
            pass
    except Exception as e:
        log.warning('Escalation create failed: %s', e)

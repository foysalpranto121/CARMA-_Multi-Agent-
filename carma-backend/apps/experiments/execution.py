"""
Resumable, case-major execution of experiment runs.

A study on a rate-limited free tier runs for days and will be interrupted.
The cases of a run are independent of each other, so an interrupted run
resumes at its first case without an outcome and ends with exactly the rows
an uninterrupted run would have.  When the model becomes unreachable the
runs are paused, not scored: an outage is not an outcome of the case.

The cases are executed case-major — every configuration runs case 1, then
every configuration runs case 2, ... — so that a drift of a hosted model
during a long study affects every configuration alike, and a study that is
cut short still has paired outcomes for all configurations.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import Adaptation, ExperimentRun
from .tasks import _push_progress, aggregate_results, persist_outcome

TUNING_NOTE = 'tau tuning on the pilot split'
RESUMABLE = ('running', 'paused')


class RunInterrupted(RuntimeError):
    """The model became unreachable; the paused runs can be resumed."""


def open_run(configuration, seed: int, cases: list, resume: bool = False,
             note: str = '') -> ExperimentRun:
    """
    The run that executes ``cases``: with ``resume``, the latest run of the
    same configuration, seed, purpose and case selection that is unfinished
    or finished (a finished run is kept as it is, so resuming twice never
    repeats a run); else a new run.
    """
    if resume:
        wanted = {case.id for case in cases}
        tuning = note.startswith(TUNING_NOTE)
        candidates = ExperimentRun.objects.filter(
            configuration=configuration, seed=seed, status__in=RESUMABLE + ('completed',),
            total_cases=len(cases)).order_by('-created_at')
        for run in candidates:
            if (run.error_log or '').startswith(TUNING_NOTE) != tuning:
                continue
            done = set(Adaptation.objects.filter(run=run)
                       .values_list('benchmark_case_id', flat=True))
            if done <= wanted:
                if run.status == 'completed':
                    return run
                run.status = 'running'
                run.error_log = (run.error_log + f'\nresumed {timezone.now():%F %T} '
                                 f'with {len(done)}/{len(cases)} cases done').strip()
                run.save(update_fields=['status', 'error_log'])
                return run
    return ExperimentRun.objects.create(
        configuration=configuration,
        process=cases[0].process if len({case.process_id for case in cases}) == 1 else None,
        seed=seed, status='running', started_at=timezone.now(),
        total_cases=len(cases), error_log=note)


def execute(jobs: list, cases: list, progress=None) -> None:
    """
    Run every case without an outcome through every job, case-major.

    :param jobs:     ``(run, runner, configuration)`` triples
    :param progress: optional callable taking a progress line
    :raises RunInterrupted: when the model is unreachable; every run is then
                            paused with its outcomes so far kept
    """
    done = {run.id: set(Adaptation.objects.filter(run=run)
                        .values_list('benchmark_case_id', flat=True))
            for run, _, _ in jobs}
    pending = {run.id for run, _, _ in jobs if run.status != 'completed'}
    for index, benchmark_case in enumerate(cases, 1):
        for run, runner, configuration in jobs:
            if benchmark_case.id in done[run.id]:
                continue
            output = runner.run(benchmark_case, configuration)
            if output.get('llm_unavailable'):
                for paused, _, _ in jobs:
                    paused.status = 'paused'
                    paused.error_log = (paused.error_log + f'\npaused {timezone.now():%F %T} '
                                        f'at case {index}/{len(cases)}: '
                                        f'{output.get("error", "")}').strip()
                    paused.save(update_fields=['status', 'error_log'])
                raise RunInterrupted(output.get('error') or 'model unreachable')
            with transaction.atomic():
                persist_outcome(run, benchmark_case, output)
            done[run.id].add(benchmark_case.id)
            _push_progress(run.id, len(cases), len(done[run.id]), 'running')
        if progress and index % 10 == 0:
            progress(f'  {index}/{len(cases)} cases …')

    for run, _, _ in jobs:
        if run.id not in pending:
            continue
        adaptations = Adaptation.objects.filter(run=run)
        run.failed_cases = adaptations.filter(status='failed').count()
        run.completed_cases = adaptations.count() - run.failed_cases
        run.save(update_fields=['completed_cases', 'failed_cases'])
        # The Celery chord callback does the aggregation; the same function
        # is used here so that both paths produce identical numbers.
        aggregate_results.apply(args=[[], str(run.id)])

"""
Run one or more experiment configurations over the WF-Adapt benchmark.

The Celery task :func:`apps.experiments.tasks.run_experiment` dispatches
one task per benchmark case.  That needs a broker and a worker; this
command performs the same work in a single process, which is what the
research protocol needs when the runs are executed one configuration at a
time and the artefacts are exported afterwards.

Usage
-----
    python manage.py run_experiment --configs B0 --seed 42
    python manage.py run_experiment --configs B0 B1 B2 B3 B4 B5 B6 B7 \
        --seed 42 --process all
    python manage.py run_experiment --configs B1 --mock-llm --limit 20

The ``--mock-llm`` flag substitutes the deterministic test double of
:mod:`carma_engine.llm.mock`.  It exercises the pipeline without a model
endpoint; a run that used it is recorded with ``llm_backend = "mock"`` and
its results are *not* model results.
"""
from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.benchmark.models import BenchmarkCase
from apps.experiments.models import Adaptation, ExperimentRun, RunConfiguration, RunResult
from apps.experiments.tasks import aggregate_results
from carma_engine.runners import get_runner


class Command(BaseCommand):
    help = 'Run experiment configurations over the WF-Adapt benchmark.'

    def add_arguments(self, parser):
        parser.add_argument('--configs', nargs='+', default=['B0'],
                            help='Configuration codes to run (B0 … B7).')
        parser.add_argument('--seed', type=int, default=42,
                            help='Random seed of the run (default 42).')
        parser.add_argument('--process', default='all',
                            help='Process id or name to run, or "all".')
        parser.add_argument('--limit', type=int, default=0,
                            help='Only run the first N benchmark cases (0 = all).')
        parser.add_argument('--mock-llm', action='store_true',
                            help='Use the deterministic test double instead of a model.')
        parser.add_argument('--reset', action='store_true',
                            help='Delete the previous run of the same configuration and seed.')

    def handle(self, *args, **options):
        codes = [str(code).upper() for code in options['configs']]
        for code in codes:
            if code not in {f'B{i}' for i in range(8)}:
                raise CommandError(f'Unknown configuration "{code}".')

        configuration = self._configuration(codes[0])
        cases = self._cases(options)
        if not cases:
            raise CommandError('No benchmark cases match the selection.')
        self.stdout.write(
            f'Running {len(codes)} configuration(s) over {len(cases)} cases '
            f'(seed {options["seed"]}).'
        )

        llm = None
        if options['mock_llm']:
            from carma_engine.llm.mock import MockLLM

            llm = MockLLM(seed=options['seed'])

        for code in codes:
            configuration = self._configuration(code)
            self._run_configuration(configuration, cases, options, llm)

    # ── helpers ────────────────────────────────────────────────
    def _configuration(self, code: str) -> RunConfiguration:
        configuration = RunConfiguration.objects.filter(code=code).first()
        if configuration is None:
            raise CommandError(
                f'Configuration {code} does not exist. Run '
                '"python manage.py seed_configurations" first.'
            )
        return configuration

    def _cases(self, options) -> list:
        queryset = BenchmarkCase.objects.filter(is_validated=True).select_related(
            'case', 'scenario', 'process', 'constraint_set')
        selector = options['process']
        if selector and selector.lower() != 'all':
            queryset = queryset.filter(process__name=selector) | queryset.filter(
                process_id=selector)
        queryset = queryset.distinct().order_by('scenario__code', 'case_id')
        limit = int(options['limit'] or 0)
        return list(queryset[:limit] if limit else queryset)

    def _run_configuration(self, configuration, cases, options, llm):
        seed = int(options['seed'])
        run = ExperimentRun.objects.filter(
            configuration=configuration, seed=seed).order_by('-created_at').first()
        if run and options['reset']:
            Adaptation.objects.filter(run=run).delete()
            RunResult.objects.filter(run=run).delete()
            run.delete()
            run = None
        if run is None:
            run = ExperimentRun.objects.create(
                configuration=configuration,
                process=cases[0].process if len({c.process_id for c in cases}) == 1 else None,
                seed=seed,
                status='running',
                started_at=timezone.now(),
                total_cases=len(cases),
            )
        else:
            run.status = 'running'
            run.started_at = timezone.now()
            run.total_cases = len(cases)
            run.completed_cases = 0
            run.failed_cases = 0
            run.error_log = ''
            run.save()

        runner = get_runner(configuration.code, config=configuration, seed=seed, llm=llm)
        started = time.monotonic()
        completed = 0
        failed = 0

        for benchmark_case in cases:
            try:
                output = runner.run(benchmark_case, configuration)
            except Exception as exc:  # pragma: no cover - defensive
                failed += 1
                self.stderr.write(f'  {benchmark_case.id}: {exc}')
                continue

            status = output.get('status') or 'failed'
            if status == 'failed':
                failed += 1
            else:
                completed += 1
            with transaction.atomic():
                Adaptation.objects.create(
                    run=run,
                    benchmark_case=benchmark_case,
                    plan_id=output.get('plan_id', ''),
                    adaptation=output.get('plan') or {},
                    activity_seq=output.get('activity_seq') or [],
                    confidence=output.get('confidence'),
                    scv_approved=output.get('scv_approved'),
                    scv_token=output.get('scv_token') or '',
                    viol_cost=float(output.get('viol_cost') or 0.0),
                    exec_cost=float(output.get('exec_cost') or 0.0),
                    total_cost=(float(output.get('viol_cost') or 0.0)
                                + float(output.get('exec_cost') or 0.0)),
                    retrieved_docs=output.get('retrieved_docs') or [],
                    retrieval_scores=output.get('retrieval_scores') or {},
                    task_success=output.get('task_success'),
                    conformance_fitness=output.get('conformance_fitness'),
                    repair_rounds=int(output.get('repair_rounds') or 0),
                    status=status,
                    latency_s=output.get('latency_s'),
                    llm_tokens=int(output.get('tokens_used') or 0),
                )
            if (completed + failed) % 100 == 0:
                self.stdout.write(f'  {completed + failed}/{len(cases)} cases …')

        run.completed_cases = completed
        run.failed_cases = failed
        run.save(update_fields=['completed_cases', 'failed_cases'])

        # The Celery chord callback does the aggregation; the same function
        # is used here so that both paths produce identical numbers.
        aggregate_results.apply(args=[[], str(run.id)])

        result = RunResult.objects.filter(run=run).first()
        elapsed = time.monotonic() - started
        self.stdout.write(
            f'{configuration.code}: {completed} completed, {failed} failed in '
            f'{elapsed:.0f}s'
        )
        if result:
            self.stdout.write(
                f'   task success {result.task_success_rate!r} | '
                f'violation rate {result.constraint_viol_rate!r} | '
                f'fitness {result.conformance_fitness!r} | '
                f'escalation {result.escalation_rate!r} | '
                f'tokens {result.total_llm_tokens}'
            )

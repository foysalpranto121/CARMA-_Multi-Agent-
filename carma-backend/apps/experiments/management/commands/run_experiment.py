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
    python manage.py run_experiment --configs B4 B7 --per-scenario 4   # 28-case pilot

The ``--mock-llm`` flag substitutes the deterministic test double of
:mod:`carma_engine.llm.mock`.  It exercises the pipeline without a model
endpoint; a run that used it is recorded with ``llm_backend = "mock"`` and
its results are *not* model results.

Without ``--mock-llm`` a configuration whose model cannot be reached (for
Claude: no ``ANTHROPIC_API_KEY`` in ``carma-backend/.env``) stops before its
first case.
"""
from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.benchmark.models import BenchmarkCase
from apps.experiments.models import Adaptation, ExperimentRun, RunConfiguration, RunResult
from apps.experiments.tasks import _push_progress, aggregate_results, persist_outcome
from carma_engine.llm.client import LLMUnavailable
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
        parser.add_argument('--per-scenario', type=int, default=0,
                            help='Only run N cases of each scenario S0-S6, taken in '
                                 'turn from each process (0 = all).')
        parser.add_argument('--mock-llm', action='store_true',
                            help='Use the deterministic test double instead of a model.')
        parser.add_argument('--reset', action='store_true',
                            help='Delete the earlier runs of the same configuration and seed.')

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

        configurations = [self._configuration(code) for code in codes]
        for configuration in configurations:
            try:
                get_runner(configuration.code, config=configuration,
                           seed=options['seed'], llm=llm).check_llm()
            except LLMUnavailable as exc:
                raise CommandError(f'{configuration.code}: {exc}') from exc

        for configuration in configurations:
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
        queryset = queryset.distinct().order_by('scenario__code', 'process_id', 'case_id')
        per_scenario = int(options.get('per_scenario') or 0)
        if per_scenario:
            return _stratified(queryset, per_scenario)
        limit = int(options['limit'] or 0)
        return list(queryset[:limit] if limit else queryset)

    def _run_configuration(self, configuration, cases, options, llm):
        seed = int(options['seed'])
        if options['reset']:
            previous = ExperimentRun.objects.filter(configuration=configuration, seed=seed)
            Adaptation.objects.filter(run__in=previous).delete()
            RunResult.objects.filter(run__in=previous).delete()
            previous.delete()
        # Every invocation is its own run: appending to an earlier run of the
        # same configuration would mix two executions in one result.
        run = ExperimentRun.objects.create(
            configuration=configuration,
            process=cases[0].process if len({c.process_id for c in cases}) == 1 else None,
            seed=seed,
            status='running',
            started_at=timezone.now(),
            total_cases=len(cases),
        )

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
                self.stderr.write(f'  {benchmark_case.id}: {output.get("error", "")}')
            else:
                completed += 1
            with transaction.atomic():
                persist_outcome(run, benchmark_case, output)
            _push_progress(run.id, len(cases), completed + failed, 'running')
            if (completed + failed) % 10 == 0:
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
        cost = sum(value for value in Adaptation.objects.filter(run=run)
                   .values_list('usd_cost', flat=True) if value)
        if cost:
            self.stdout.write(f'   list-price cost ${cost:.2f}')


def _stratified(queryset, per_scenario: int) -> list:
    """
    ``per_scenario`` cases of every scenario, taken in turn from each process,
    so that a small pilot still covers every scenario and every process.
    """
    cells: dict = {}
    for benchmark_case in queryset:
        cells.setdefault(benchmark_case.scenario.code, {}).setdefault(
            str(benchmark_case.process_id), []).append(benchmark_case)

    chosen = []
    for code in sorted(cells):
        queues = [cells[code][process] for process in sorted(cells[code])]
        picked, index = [], 0
        while len(picked) < per_scenario and any(index < len(queue) for queue in queues):
            for queue in queues:
                if index < len(queue) and len(picked) < per_scenario:
                    picked.append(queue[index])
            index += 1
        chosen.extend(picked)
    return chosen

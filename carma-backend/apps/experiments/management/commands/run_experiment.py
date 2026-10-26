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
    python manage.py run_experiment --configs B4 B5 B6 B7 --model openai/gpt-oss-120b \
        --seed 42 --per-scenario 28                     # the confirmatory sample
    python manage.py run_experiment ... --resume        # continue a paused run
    python manage.py run_experiment --configs B1 --mock-llm --limit 20

The configurations run case-major (every configuration runs a case before
the next case starts) and each case is stored as soon as it ends; see
:mod:`apps.experiments.execution`.  When the model becomes unreachable the
runs are paused; the same command with ``--resume`` continues them.

The ``--mock-llm`` flag substitutes the deterministic test double of
:mod:`carma_engine.llm.mock`.  It exercises the pipeline without a model
endpoint; a run that used it is recorded with ``llm_backend = "mock"`` and
its results are *not* model results.

Without ``--mock-llm`` a configuration whose model cannot be reached (for
Groq: no ``GROQ_API_KEY`` in ``carma-backend/.env``) stops before its
first case.
"""
from __future__ import annotations

import time

from decouple import config
from django.core.management.base import BaseCommand, CommandError

from apps.benchmark.models import BenchmarkCase
from apps.experiments.execution import RunInterrupted, execute, open_run
from apps.experiments.models import Adaptation, ExperimentRun, RunConfiguration, RunResult
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
        parser.add_argument('--model', default='',
                            help='LLM of the configurations to run (their llm_model).')
        parser.add_argument('--split', choices=['eval', 'pilot'], default='eval',
                            help='Benchmark split: eval (the study) or pilot (tuning only).')
        parser.add_argument('--per-scenario', type=int, default=0,
                            help='Only run N cases of each scenario S0-S6, taken in '
                                 'turn from each process (0 = all).')
        parser.add_argument('--mock-llm', action='store_true',
                            help='Use the deterministic test double instead of a model.')
        parser.add_argument('--resume', action='store_true',
                            help='Continue the unfinished run of each configuration and '
                                 'seed over the same cases (a finished one is kept) '
                                 'instead of starting a new one.')
        parser.add_argument('--reset', action='store_true',
                            help='Delete the earlier runs of the same configuration and seed.')

    def handle(self, *args, **options):
        codes = [str(code).upper() for code in options['configs']]
        for code in codes:
            if code not in {f'B{i}' for i in range(8)}:
                raise CommandError(f'Unknown configuration "{code}".')

        self.model = options.get('model') or ''
        cases = self._cases(options)
        if not cases:
            raise CommandError('No benchmark cases match the selection.')
        seed = int(options['seed'])
        self.stdout.write(
            f'Running {len(codes)} configuration(s) over {len(cases)} cases (seed {seed}).')

        llm = None
        if options['mock_llm']:
            from carma_engine.llm.mock import MockLLM

            llm = MockLLM(seed=seed)

        jobs = []
        for code in codes:
            configuration = self._configuration(code)
            runner = get_runner(configuration.code, config=configuration, seed=seed, llm=llm)
            try:
                runner.check_llm()
            except LLMUnavailable as exc:
                raise CommandError(f'{configuration.code}: {exc}') from exc
            jobs.append((None, runner, configuration))

        # The protocol is registered before any model sees an evaluation case.
        registration = str(config('PREREGISTRATION_URL', default='')).strip()
        if (options.get('split') or 'eval') == 'eval' and not options['mock_llm'] \
                and not registration and any(runner.uses_llm for _, runner, _ in jobs):
            raise CommandError(
                'The evaluation split runs only after the study is registered: set '
                'PREREGISTRATION_URL in carma-backend/.env to the OSF registration. '
                'Meanwhile use --split pilot or --mock-llm.')

        for index, (_, runner, configuration) in enumerate(jobs):
            if options['reset']:
                previous = ExperimentRun.objects.filter(configuration=configuration, seed=seed)
                Adaptation.objects.filter(run__in=previous).delete()
                RunResult.objects.filter(run__in=previous).delete()
                previous.delete()
            run = open_run(configuration, seed, cases, resume=options['resume'],
                           note=f'preregistration {registration}' if registration else '')
            jobs[index] = (run, runner, configuration)
            self.stdout.write(f'  {configuration.code}: run {run.id}')

        started = time.monotonic()
        try:
            execute(jobs, cases, progress=self.stdout.write)
        except RunInterrupted as exc:
            raise CommandError(f'Paused, the outcomes so far are kept ({exc}). '
                               'Run the same command with --resume to continue.') from exc
        self.stdout.write(f'Done in {time.monotonic() - started:.0f}s.')
        for run, _, configuration in jobs:
            self._report(run, configuration)

    # ── helpers ────────────────────────────────────────────────
    def _configuration(self, code: str) -> RunConfiguration:
        queryset = RunConfiguration.objects.filter(code=code)
        if getattr(self, 'model', ''):
            queryset = queryset.filter(llm_model=self.model)
        configuration = queryset.order_by('created_at').first()
        if configuration is None:
            raise CommandError(
                f'Configuration {code} does not exist. Run '
                '"python manage.py seed_configurations" first.'
            )
        return configuration

    def _cases(self, options) -> list:
        queryset = BenchmarkCase.objects.filter(
            is_validated=True, split=options.get('split') or 'eval').select_related(
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

    def _report(self, run, configuration):
        run.refresh_from_db()
        self.stdout.write(f'{configuration.code}: {run.completed_cases} completed, '
                          f'{run.failed_cases} failed')
        result = RunResult.objects.filter(run=run).first()
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

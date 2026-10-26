"""
Tune the escalation threshold tau on the pilot split.

    python manage.py tune_tau [--config B7] [--seed 42]

tau is the only hyper-parameter tuned (the protocol tunes on a 10 % pilot
split only).  The configuration runs once on the pilot split with the
confidence gate off (tau = 0); every tau of the grid is then replayed
offline: a case whose plan confidence is below tau would have gone to a
human instead of running.  The other reasons to escalate do not depend on
tau, so the replay is exact.  The tau with the highest pilot task success is
written to every configuration (ties: the smaller tau, fewer escalations).
The evaluation split is never touched.
"""
import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.benchmark.models import BenchmarkCase
from apps.experiments.models import Adaptation, ExperimentRun, RunConfiguration
from apps.experiments.tasks import aggregate_results, persist_outcome
from carma_engine.llm.client import LLMUnavailable
from carma_engine.runners import get_runner
from carma_engine.runners.base import _end_activities
from carma_engine.scoring import score_adaptation

GRID = [round(0.1 * step, 1) for step in range(10)]


def replay(rows: list, tau: float) -> dict:
    """Pilot task success and escalation rate had the gate used ``tau``."""
    successes = escalations = 0
    for benchmark_case, adaptation in rows:
        confidence = (adaptation.adaptation or {}).get('confidence')
        gated = (adaptation.status not in ('escalated', 'failed') and adaptation.planned_seq
                 and confidence is not None and float(confidence) < tau)
        if gated:
            success = score_adaptation(
                benchmark_case.gold_adaptation, benchmark_case.gold_activity_seq, [],
                'escalated', False,
                end_activities=_end_activities(benchmark_case.process)).task_success
        else:
            success = bool(adaptation.task_success)
        successes += int(success)
        escalations += int(gated or adaptation.status == 'escalated')
    return {'tau': tau,
            'task_success_rate': successes / len(rows),
            'escalation_rate': escalations / len(rows)}


class Command(BaseCommand):
    help = 'Tune the escalation threshold tau on the pilot split.'

    def add_arguments(self, parser):
        parser.add_argument('--config', default='B7')
        parser.add_argument('--model', required=True,
                            help='LLM to tune for: tau is calibrated on its confidences.')
        parser.add_argument('--seed', type=int, default=42)
        parser.add_argument('--output', default='../artifacts/tuning')

    def handle(self, *args, **options):
        configuration = RunConfiguration.objects.filter(
            code=options['config'], llm_model=options['model']).first()
        if configuration is None:
            raise CommandError(f'Configuration {options["config"]} does not exist.')
        cases = list(BenchmarkCase.objects.filter(is_validated=True, split='pilot')
                     .select_related('case', 'scenario', 'process', 'constraint_set')
                     .order_by('scenario__code', 'process_id', 'case_id'))
        if not cases:
            raise CommandError('No pilot cases: rebuild the benchmark with --pilot-cases.')

        configuration.tau_threshold = 0.0  # in memory only: the confidence gate is off
        runner = get_runner(configuration.code, config=configuration, seed=options['seed'])
        try:
            runner.check_llm()
        except LLMUnavailable as exc:
            raise CommandError(str(exc)) from exc

        run = ExperimentRun.objects.create(
            configuration=configuration, seed=options['seed'], status='running',
            started_at=timezone.now(), total_cases=len(cases),
            error_log='tau tuning on the pilot split, confidence gate off (tau = 0)')
        self.stdout.write(f'Running {configuration.code} on {len(cases)} pilot cases …')
        for benchmark_case in cases:
            persist_outcome(run, benchmark_case, runner.run(benchmark_case, configuration))
        aggregate_results.apply(args=[[], str(run.id)])

        rows = [(adaptation.benchmark_case, adaptation) for adaptation in
                Adaptation.objects.filter(run=run).select_related(
                    'benchmark_case__process', 'benchmark_case__scenario')]
        results = [replay(rows, tau) for tau in GRID]
        best = max(results, key=lambda result: (result['task_success_rate'], -result['tau']))

        for result in results:
            marker = '  <- chosen' if result is best else ''
            self.stdout.write(f"  tau={result['tau']:.1f}  task success "
                              f"{result['task_success_rate']:.3f}  escalation "
                              f"{result['escalation_rate']:.3f}{marker}")
        RunConfiguration.objects.filter(llm_model=options['model']).update(
            tau_threshold=best['tau'])

        os.makedirs(options['output'], exist_ok=True)
        path = os.path.join(options['output'],
                            f"tau_{options['model'].replace('/', '_')}.json")
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump({'run_id': str(run.id), 'configuration': configuration.code,
                       'pilot_cases': len(rows), 'grid': results, 'chosen_tau': best['tau'],
                       'criterion': 'max pilot task success; ties -> smaller tau'},
                      handle, indent=2)
        self.stdout.write(self.style.SUCCESS(
            f"tau = {best['tau']} written to every configuration; report: {path}"))

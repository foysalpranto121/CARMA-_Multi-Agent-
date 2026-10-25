"""
Statistical analysis of the experiment runs.

Reads the adaptations of the stored runs, pairs them by benchmark case and
applies the pre-registered analysis plan:

* McNemar (exact, Holm-corrected) on the binary outcomes — constraint
  violated and task success;
* Friedman with Wilcoxon post-hoc (Holm-corrected) on the continuous
  outcomes — violation cost, execution cost, latency and token use;
* bootstrap confidence intervals for every reported mean.

The command writes a machine-readable JSON file and a Markdown summary, so
that the numbers in the report can be traced back to the stored runs.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from apps.experiments.models import Adaptation, ExperimentRun
from apps.metrics.services.stats import (
    bootstrap_ci,
    friedman_test,
    mcnemar_pairwise,
    posthoc_wilcoxon,
)

#: Continuous outcomes analysed with the Friedman test.
CONTINUOUS_OUTCOMES = (
    ('viol_cost', 'Violation cost'),
    ('exec_cost', 'Execution cost'),
    ('latency_s', 'Latency (s)'),
    ('llm_tokens', 'LLM tokens'),
)

#: Binary outcomes analysed with the McNemar test.
BINARY_OUTCOMES = (
    ('constraint_violated', 'Constraint violated'),
    ('task_succeeded', 'Task succeeded'),
)


class Command(BaseCommand):
    help = 'Analyse the experiment runs and write the statistics report.'

    def add_arguments(self, parser):
        parser.add_argument('--runs', nargs='*', default=[],
                            help='Run ids to analyse (default: every completed run).')
        parser.add_argument('--output', default='artifacts/analysis',
                            help='Directory the report is written to.')
        parser.add_argument('--seed', type=int, default=42,
                            help='Seed of the bootstrap resampling.')
        parser.add_argument('--include-mock', action='store_true',
                            help='Also analyse adaptations made with the test double.')

    def handle(self, *args, **options):
        runs = self._runs(options['runs'])
        if not runs:
            raise CommandError('No completed runs to analyse.')

        rows = []
        for run in runs:
            adaptations = Adaptation.objects.filter(run=run).select_related('benchmark_case')
            # A run on the test double measures the plumbing, never a model.
            if not options['include_mock']:
                adaptations = adaptations.exclude(llm_backend='mock')
            for adaptation in adaptations:
                rows.append({
                    'run_id': str(run.id),
                    'config_code': run.configuration.code,
                    'seed': run.seed,
                    'benchmark_case_id': str(adaptation.benchmark_case_id),
                    'scenario': adaptation.benchmark_case.scenario.code,
                    'constraint_violated': adaptation.constraint_violated,
                    'task_succeeded': adaptation.task_success,
                    'gold_exact_match': adaptation.gold_exact_match,
                    'gold_similarity': adaptation.gold_similarity,
                    'unsafe_action': adaptation.unsafe_action,
                    'usd_cost': adaptation.usd_cost,
                    'escalated': adaptation.status == 'escalated',
                    'repaired': adaptation.repair_rounds > 0,
                    'viol_cost': adaptation.viol_cost,
                    'exec_cost': adaptation.exec_cost,
                    'latency_s': adaptation.latency_s,
                    'llm_tokens': adaptation.llm_tokens,
                    'conformance_fitness': adaptation.conformance_fitness,
                })

        analysis = self._analyse(rows, options['seed'])
        analysis['runs'] = [
            {
                'run_id': str(run.id),
                'config_code': run.configuration.code,
                'seed': run.seed,
                'cases': run.total_cases,
                'completed': run.completed_cases,
                'status': run.status,
            }
            for run in runs
        ]

        directory = options['output']
        os.makedirs(directory, exist_ok=True)
        json_path = os.path.join(directory, 'statistics.json')
        with open(json_path, 'w', encoding='utf-8') as handle:
            json.dump(analysis, handle, indent=2, default=str)
        markdown_path = os.path.join(directory, 'statistics.md')
        with open(markdown_path, 'w', encoding='utf-8') as handle:
            handle.write(render_markdown(analysis))

        self.stdout.write(self.style.SUCCESS(
            f'Wrote {json_path} and {markdown_path} '
            f'({len(rows)} observations over {len(runs)} runs).'
        ))

    # ── helpers ────────────────────────────────────────────────
    def _runs(self, run_ids) -> list:
        queryset = ExperimentRun.objects.filter(status='completed').select_related(
            'configuration')
        if run_ids:
            queryset = queryset.filter(id__in=run_ids)
        return list(queryset.order_by('configuration__code', 'seed'))

    def _analyse(self, rows: list, seed: int) -> dict:
        by_config: dict[str, list] = defaultdict(list)
        for row in rows:
            by_config[row['config_code']].append(row)

        summary = {}
        for config, config_rows in sorted(by_config.items()):
            n = len(config_rows)
            violated = sum(1 for row in config_rows if row['constraint_violated'])
            succeeded = sum(1 for row in config_rows if row['task_succeeded'])
            escalated = sum(1 for row in config_rows if row['escalated'])
            summary[config] = {
                'n': n,
                'constraint_violation_rate': violated / n if n else None,
                'task_success_rate': succeeded / n if n else None,
                'escalation_rate': escalated / n if n else None,
                'mean_violation_cost': _mean([r['viol_cost'] for r in config_rows]),
                'mean_exec_cost': _mean([r['exec_cost'] for r in config_rows]),
                'mean_latency_s': _mean([r['latency_s'] for r in config_rows]),
                'mean_llm_tokens': _mean([r['llm_tokens'] for r in config_rows]),
                'mean_conformance_fitness': _mean(
                    [r['conformance_fitness'] for r in config_rows]),
                'violation_cost_ci': bootstrap_ci(
                    [r['viol_cost'] for r in config_rows], seed=seed),
                'latency_ci': bootstrap_ci(
                    [r['latency_s'] for r in config_rows
                     if r['latency_s'] is not None], seed=seed),
            }

        # Pair the observations by benchmark case so that the tests are
        # repeated-measures tests on the same cases.
        paired_rows = []
        index: dict[tuple, dict] = {}
        for row in rows:
            index[(row['config_code'], row['benchmark_case_id'])] = row
        case_ids = sorted({row['benchmark_case_id'] for row in rows})
        for case_id in case_ids:
            for config in sorted(by_config):
                row = index.get((config, case_id))
                if row is not None:
                    paired_rows.append(row)

        mcnemar = {}
        for outcome, label in BINARY_OUTCOMES:
            mcnemar[outcome] = mcnemar_pairwise(paired_rows, outcome=outcome)

        continuous = {}
        for outcome, label in CONTINUOUS_OUTCOMES:
            samples = {}
            for config in sorted(by_config):
                values = [row[outcome] for row in paired_rows
                          if row['config_code'] == config
                          and row.get(outcome) is not None]
                if values:
                    samples[config] = values
            if len(samples) < 3:
                continuous[outcome] = {'error': 'Fewer than three configurations.'}
                continue
            continuous[outcome] = {
                'friedman': friedman_test(samples),
                'posthoc': posthoc_wilcoxon(samples),
            }

        per_scenario = {}
        for config, config_rows in sorted(by_config.items()):
            buckets = defaultdict(list)
            for row in config_rows:
                buckets[row['scenario']].append(row)
            per_scenario[config] = {
                scenario: {
                    'n': len(scenario_rows),
                    'constraint_violation_rate': sum(
                        1 for r in scenario_rows if r['constraint_violated']) / len(scenario_rows),
                    'task_success_rate': sum(
                        1 for r in scenario_rows if r['task_succeeded']) / len(scenario_rows),
                    'escalation_rate': sum(
                        1 for r in scenario_rows if r['escalated']) / len(scenario_rows),
                }
                for scenario, scenario_rows in sorted(buckets.items())
            }

        return {
            'n_observations': len(rows),
            'n_cases': len(case_ids),
            'summary': summary,
            'per_scenario': per_scenario,
            'mcnemar': mcnemar,
            'continuous': continuous,
        }


def _mean(values) -> float | None:
    numbers = [float(v) for v in values if v is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def render_markdown(analysis: dict) -> str:
    """Render the analysis as a Markdown report."""
    lines = ['# WF-Adapt — experiment analysis', '']
    lines.append(f"Observations: **{analysis['n_observations']}** over "
                 f"**{analysis['n_cases']}** benchmark cases.")
    lines.append('')
    lines.append('## Configuration summary')
    lines.append('')
    lines.append('| Config | n | Violation rate | Task success | Escalation | '
                 'Mean viol. cost | Mean latency (s) | Mean tokens |')
    lines.append('|---|---|---|---|---|---|---|---|')
    for config, entry in analysis['summary'].items():
        lines.append(
            f"| {config} | {entry['n']} | "
            f"{_fmt(entry['constraint_violation_rate'])} | "
            f"{_fmt(entry['task_success_rate'])} | "
            f"{_fmt(entry['escalation_rate'])} | "
            f"{_fmt(entry['mean_violation_cost'], 3)} | "
            f"{_fmt(entry['mean_latency_s'], 3)} | "
            f"{_fmt(entry['mean_llm_tokens'], 1)} |"
        )
    lines.append('')

    lines.append('## McNemar tests (paired, Holm-corrected)')
    lines.append('')
    for outcome, results in analysis.get('mcnemar', {}).items():
        lines.append(f'### {outcome}')
        lines.append('')
        if not results:
            lines.append('No paired comparison available.')
            lines.append('')
            continue
        lines.append('| A | B | only A | only B | p | p (Holm) | significant |')
        lines.append('|---|---|---|---|---|---|---|')
        for result in results:
            outcome_values = result['outcome']
            lines.append(
                f"| {result['config_a']} | {result['config_b']} | "
                f"{outcome_values.get('only_a')} | {outcome_values.get('only_b')} | "
                f"{_fmt(outcome_values.get('p_value'), 4)} | "
                f"{_fmt(outcome_values.get('p_corrected'), 4)} | "
                f"{'yes' if outcome_values.get('significant_after_correction') else 'no'} |"
            )
        lines.append('')

    lines.append('## Friedman tests with Wilcoxon post-hoc')
    lines.append('')
    for outcome, entry in analysis.get('continuous', {}).items():
        lines.append(f'### {outcome}')
        lines.append('')
        if 'error' in entry:
            lines.append(f"*{entry['error']}*")
            lines.append('')
            continue
        friedman = entry['friedman']
        lines.append(f"Friedman: statistic {friedman.get('statistic')}, "
                     f"p {friedman.get('p_value')}, "
                     f"{friedman.get('n_blocks')} blocks.")
        lines.append('')
        lines.append('| A | B | W | p | p (Holm) | Cliff delta | significant |')
        lines.append('|---|---|---|---|---|---|---|')
        for result in entry['posthoc']:
            if 'error' in result:
                continue
            lines.append(
                f"| {result['config_a']} | {result['config_b']} | "
                f"{_fmt(result.get('statistic'), 1)} | "
                f"{_fmt(result.get('p_value'), 4)} | "
                f"{_fmt(result.get('p_corrected'), 4)} | "
                f"{_fmt(result.get('cliff_delta'), 3)} | "
                f"{'yes' if result.get('significant_after_correction') else 'no'} |"
            )
        lines.append('')

    lines.append('## Per-scenario results')
    lines.append('')
    for config, scenarios in analysis.get('per_scenario', {}).items():
        lines.append(f'### {config}')
        lines.append('')
        lines.append('| Scenario | n | Violation rate | Task success | Escalation |')
        lines.append('|---|---|---|---|---|')
        for scenario, entry in scenarios.items():
            lines.append(
                f"| {scenario} | {entry['n']} | "
                f"{_fmt(entry['constraint_violation_rate'])} | "
                f"{_fmt(entry['task_success_rate'])} | "
                f"{_fmt(entry['escalation_rate'])} |"
            )
        lines.append('')
    return '\n'.join(lines) + '\n'


def _fmt(value, digits: int = 3) -> str:
    if value is None:
        return '—'
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    try:
        return f'{float(value):.{digits}f}'
    except (TypeError, ValueError):
        return str(value)

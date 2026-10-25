"""
Export the research artefact bundle.

The bundle is the reproducible record of the study: the event logs it was
built on, the discovered process models, the mined frames, the benchmark
cases, the knowledge corpus, the experiment runs and the statistics.

Everything is written as plain, inspectable files (JSON, CSV, Markdown,
XES) so that the bundle can be re-analysed without the platform.

Usage
-----
    python manage.py export_artifacts --output ../artifacts/wf-adapt
    python manage.py export_artifacts --output ../artifacts/wf-adapt \
        --include-logs
"""
from __future__ import annotations

import csv
import json
import os
import shutil
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.benchmark.models import BenchmarkCase, BenchmarkScenario, Case, EventLog
from apps.experiments.models import Adaptation, ExperimentRun, RunConfiguration, RunResult
from apps.processes.models import Constraint, ConstraintSet, CorpusDocument, Process


class Command(BaseCommand):
    help = 'Export the research artefact bundle (logs, models, frames, cases, results).'

    def add_arguments(self, parser):
        parser.add_argument('--output', default='../artifacts/wf-adapt',
                            help='Directory the bundle is written to.')
        parser.add_argument('--include-logs', action='store_true',
                            help='Copy the source XES logs into the bundle (large).')
        parser.add_argument('--data-dir', default=None,
                            help='Directory the source XES logs live in (default: ./data).')

    def handle(self, *args, **options):
        output = os.path.abspath(options['output'])
        os.makedirs(output, exist_ok=True)
        written = []

        written += self._write_manifest(output)
        written += self._write_logs(output, options)
        written += self._write_processes(output)
        written += self._write_frames(output)
        written += self._write_corpus(output)
        written += self._write_cases(output)
        written += self._write_benchmark(output)
        written += self._write_results(output)
        written += self._write_readme(output)

        self.stdout.write(self.style.SUCCESS(
            f'Artifact bundle written to {output} ({len(written)} files).'))

    # ── parts ──────────────────────────────────────────────────
    def _write_manifest(self, output: str) -> list[str]:
        manifest = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'platform': 'CARMA — Constraint-Aware Retrieval-augmented Multi-Agent adaptation',
            'benchmark': 'WF-Adapt',
            'python': os.sys.version,
            'components': {},
        }
        counts = {
            'event_logs': EventLog.objects.count(),
            'processes': Process.objects.count(),
            'constraint_sets': ConstraintSet.objects.count(),
            'constraints': Constraint.objects.count(),
            'corpus_documents': CorpusDocument.objects.count(),
            'cases': Case.objects.count(),
            'benchmark_cases': BenchmarkCase.objects.count(),
            'validated_benchmark_cases': BenchmarkCase.objects.filter(is_validated=True).count(),
            'scenarios': BenchmarkScenario.objects.count()(),
            'run_configurations': RunConfiguration.objects.count(),
            'experiment_runs': ExperimentRun.objects.count(),
            'adaptations': Adaptation.objects.count(),
        }
        manifest['components'] = counts
        path = os.path.join(output, 'manifest.json')
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(manifest, handle, indent=2, default=str)
        return [path]

    def _write_logs(self, output: str, options) -> list[str]:
        logs_dir = os.path.join(output, 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        written = []
        for event_log in EventLog.objects.all():
            record = {
                'name': event_log.name,
                'source': event_log.source,
                'file': event_log.file_path,
                'case_count': Case.objects.filter(event_log=event_log).count(),
                'train_cases': Case.objects.filter(
                    event_log=event_log, attributes__split='train').count(),
                'test_cases': Case.objects.filter(
                    event_log=event_log, attributes__split='test').count(),
            }
            path = os.path.join(logs_dir, f"{_slug(event_log.name)}.json")
            with open(path, 'w', encoding='utf-8') as handle:
                json.dump(record, handle, indent=2, default=str)
            written.append(path)

        if options['include_logs']:
            data_dir = options['data_dir'] or os.path.join(
                os.path.dirname(os.path.abspath('.')), 'data')
            for event_log in EventLog.objects.all():
                source = event_log.file_path
                if not source or not os.path.exists(source):
                    continue
                target = os.path.join(logs_dir, os.path.basename(source))
                shutil.copy2(source, target)
                written.append(target)
        return written

    def _write_processes(self, output: str) -> list[str]:
        directory = os.path.join(output, 'processes')
        os.makedirs(directory, exist_ok=True)
        written = []
        for process in Process.objects.all():
            path = os.path.join(directory, f"{_slug(process.name)}.json")
            payload = {
                'id': str(process.id),
                'name': process.name,
                'description': process.description,
                'activities': process.activities,
                'model_xml': process.model_xml,
                'created_at': process.created_at.isoformat() if process.created_at else None,
            }
            with open(path, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle, indent=2, default=str)
            written.append(path)
        return written

    def _write_frames(self, output: str) -> list[str]:
        directory = os.path.join(output, 'frames')
        os.makedirs(directory, exist_ok=True)
        written = []
        for constraint_set in ConstraintSet.objects.all():
            path = os.path.join(directory, f"{_slug(constraint_set.name)}.json")
            payload = {
                'id': str(constraint_set.id),
                'name': constraint_set.name,
                'version': constraint_set.version,
                'process': constraint_set.process.name,
                'is_active': constraint_set.is_active,
                'constraints': [
                    {
                        'id': str(constraint.id),
                        'type': constraint.constraint_type,
                        'activity_a': constraint.activity_a,
                        'activity_b': constraint.activity_b,
                        'parameters': constraint.parameters,
                        'violation_cost': constraint.violation_cost,
                        'description': constraint.description,
                    }
                    for constraint in constraint_set.constraints.all()
                ],
            }
            with open(path, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle, indent=2, default=str)
            written.append(path)
        return written

    def _write_corpus(self, output: str) -> list[str]:
        directory = os.path.join(output, 'corpus')
        os.makedirs(directory, exist_ok=True)
        written = []
        for process in Process.objects.all():
            path = os.path.join(directory, f"{_slug(process.name)}.jsonl")
            with open(path, 'w', encoding='utf-8') as handle:
                for document in CorpusDocument.objects.filter(process=process):
                    handle.write(json.dumps({
                        'doc_id': str(document.id),
                        'title': document.title,
                        'doc_type': document.doc_type,
                        'stage': document.stage,
                        'content': document.content,
                        'metadata': document.metadata,
                    }, default=str) + '\n')
            written.append(path)
        return written

    def _write_cases(self, output: str) -> list[str]:
        directory = os.path.join(output, 'cases')
        os.makedirs(directory, exist_ok=True)
        written = []
        for event_log in EventLog.objects.all():
            path = os.path.join(directory, f"{_slug(event_log.name)}.jsonl")
            with open(path, 'w', encoding='utf-8') as handle:
                for case in Case.objects.filter(event_log=event_log):
                    handle.write(json.dumps({
                        'case_id': case.case_id,
                        'split': (case.attributes or {}).get('split'),
                        'attributes': case.attributes,
                        'prefix_trace': case.prefix_trace,
                    }, default=str) + '\n')
            written.append(path)
        return written

    def _write_benchmark(self, output: str) -> list[str]:
        directory = os.path.join(output, 'benchmark')
        os.makedirs(directory, exist_ok=True)
        written = []

        rows = []
        for benchmark_case in BenchmarkCase.objects.select_related(
                'case', 'scenario', 'process', 'constraint_set'):
            rows.append({
                'case_id': benchmark_case.case.case_id,
                'process': benchmark_case.process.name,
                'scenario': benchmark_case.scenario.code,
                'scenario_name': benchmark_case.scenario.name,
                'split': (benchmark_case.case.attributes or {}).get('split'),
                'prefix_trace': benchmark_case.prefix_trace,
                'gold_activity_seq': benchmark_case.gold_activity_seq,
                'perturbation': benchmark_case.perturbation,
                'perturbation_text': benchmark_case.perturbation_text,
                'is_validated': benchmark_case.is_validated,
            })
        path = os.path.join(directory, 'benchmark_cases.jsonl')
        with open(path, 'w', encoding='utf-8') as handle:
            for row in rows:
                handle.write(json.dumps(row, default=str) + '\n')
        written.append(path)

        path = os.path.join(directory, 'benchmark_cases.csv')
        with open(path, 'w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['case_id', 'process', 'scenario', 'split',
                             'prefix_length', 'gold_length', 'validated'])
            for row in rows:
                writer.writerow([
                    row['case_id'], row['process'], row['scenario'], row['split'],
                    len(row['prefix_trace'] or []), len(row['gold_activity_seq'] or []),
                    row['is_validated'],
                ])
        written.append(path)

        path = os.path.join(directory, 'scenarios.json')
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump([
                {
                    'code': scenario.code,
                    'name': scenario.name,
                    'description': scenario.description,
                    'perturbation_type': scenario.perturbation_type,
                    'parameters': scenario.parameters,
                }
                for scenario in Scenario.objects.all().order_by('code')
            ], handle, indent=2, default=str)
        written.append(path)
        return written

    def _write_results(self, output: str) -> list[str]:
        directory = os.path.join(output, 'results')
        os.makedirs(directory, exist_ok=True)
        written = []

        path = os.path.join(directory, 'runs.json')
        rows = []
        for run in ExperimentRun.objects.select_related('configuration'):
            result = RunResult.objects.filter(run=run).first()
            rows.append({
                'run_id': str(run.id),
                'config_code': run.configuration.code,
                'config_name': run.configuration.name,
                'llm_model': run.configuration.llm_model,
                'seed': run.seed,
                'status': run.status,
                'total_cases': run.total_cases,
                'completed_cases': run.completed_cases,
                'failed_cases': run.failed_cases,
                'started_at': run.started_at.isoformat() if run.started_at else None,
                'completed_at': run.completed_at.isoformat() if run.completed_at else None,
                'task_success_rate': result.task_success_rate if result else None,
                'constraint_viol_rate': result.constraint_viol_rate if result else None,
                'conformance_fitness': result.conformance_fitness if result else None,
                'escalation_rate': result.escalation_rate if result else None,
                'mean_latency_s': result.mean_latency_s if result else None,
                'total_llm_tokens': result.total_llm_tokens if result else None,
            })
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(rows, handle, indent=2, default=str)
        written.append(path)

        path = os.path.join(directory, 'adaptations.csv')
        with open(path, 'w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow([
                'run_id', 'config_code', 'seed', 'case_id', 'process', 'scenario',
                'status', 'viol_cost', 'exec_cost', 'task_success',
                'conformance_fitness', 'repair_rounds', 'escalated',
                'latency_s', 'llm_tokens', 'plan_activities',
                'hard_violation', 'unsafe_action', 'gold_exact_match',
                'gold_similarity', 'planned_activities', 'plan_source',
                'llm_backend', 'served_by', 'usd_cost'])
            for adaptation in Adaptation.objects.select_related(
                    'run__configuration', 'benchmark_case__case',
                    'benchmark_case__scenario', 'benchmark_case__process'):
                writer.writerow([
                    str(adaptation.run_id),
                    adaptation.run.configuration.code,
                    adaptation.run.seed,
                    adaptation.benchmark_case.case.case_id,
                    adaptation.benchmark_case.process.name,
                    adaptation.benchmark_case.scenario.code,
                    adaptation.status,
                    adaptation.viol_cost,
                    adaptation.exec_cost,
                    adaptation.task_success,
                    adaptation.conformance_fitness,
                    adaptation.repair_rounds,
                    adaptation.status == 'escalated',
                    adaptation.latency_s,
                    adaptation.llm_tokens,
                    '|'.join(adaptation.activity_seq or []),
                    adaptation.constraint_violated,
                    adaptation.unsafe_action,
                    adaptation.gold_exact_match,
                    adaptation.gold_similarity,
                    '|'.join(adaptation.planned_seq or []),
                    adaptation.plan_source,
                    adaptation.llm_backend,
                    json.dumps(adaptation.served_by or {}, sort_keys=True),
                    adaptation.usd_cost,
                ])
        written.append(path)
        return written

    def _write_readme(self, output: str) -> list[str]:
        counts = {
            'event_logs': EventLog.objects.count(),
            'benchmark_cases': BenchmarkCase.objects.filter(is_validated=True).count(),
            'adaptations': Adaptation.objects.count(),
            'experiment_runs': ExperimentRun.objects.count(),
        }
        text = f"""# WF-Adapt artefact bundle

Generated {datetime.now(timezone.utc).isoformat()}.

This bundle is the reproducible record of the CARMA study on workflow
adaptation.  It contains everything the analysis needs, in plain files:

| Path | Content |
|---|---|
| `manifest.json` | what the bundle contains and when it was generated |
| `logs/` | one record per source event log, with the train/test split sizes |
| `processes/` | the discovered process models (PMML) and their activities |
| `frames/` | the mined frames (Declare constraints and policy rules) per process |
| `corpus/` | the knowledge corpus K — SOPs, rule cards and precedents |
| `cases/` | the imported cases with their train/test split |
| `benchmark/` | the WF-Adapt benchmark cases, their scenarios and perturbations |
| `results/` | the experiment runs, their aggregates and every single adaptation |
| `statistics/` | the statistical analysis (JSON and Markdown) |

Current size: {counts['event_logs']} event logs, {counts['benchmark_cases']}
validated benchmark cases, {counts['experiment_runs']} experiment runs,
{counts['adaptations']} recorded adaptations.

## Reading the results

`results/runs.json` holds one row per experiment run with the aggregate
metrics; `results/adaptations.csv` holds one row per benchmark case and
run, which is the granularity the paired (McNemar / Friedman) tests need.
`statistics/statistics.md` is the rendered analysis.

## Reproducing

    python manage.py import_benchmark --datasets bpi2017 bpi2019 bpi2020 rtfm \\
        --cases-per-scenario 30 --seed 42
    python manage.py seed_configurations
    python manage.py run_experiment --configs B0 B1 B2 B3 B4 B5 B6 B7 --seed 42
    python manage.py analyse_experiment --output ../artifacts/wf-adapt/statistics
    python manage.py export_artifacts --output ../artifacts/wf-adapt

The LLM-based configurations need a reachable model endpoint
(`ANTHROPIC_API_KEY` for Claude, `OPENAI_API_KEY` or `OLLAMA_BASE_URL`);
without one the platform refuses to record model output: the run stops
before its first case instead of falling back to the rule-based behaviour.
"""
        path = os.path.join(output, 'README.md')
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        return [path]


def _slug(value: str) -> str:
    """A file-system safe name."""
    keep = []
    for character in (value or ''):
        if character.isalnum() or character in '-_.':
            keep.append(character)
        else:
            keep.append('_')
    return ''.join(keep).strip('_') or 'unnamed'

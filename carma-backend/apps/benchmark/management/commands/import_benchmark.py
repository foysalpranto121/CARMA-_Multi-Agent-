"""
Build the WF-Adapt benchmark from the public event logs.

The command performs the full pipeline for one or more datasets:

  1. import the XES event log and split it by time (70 % train / 30 % test);
  2. discover a control-flow model with the Inductive Miner on the *training*
     split and store it as the procedural model M;
  3. mine the Declare constraints D and derive the policy rules P from the
     same split;
  4. build the SOP corpus K from the training split;
  5. build the seven perturbation scenarios S0-S6 over the test split.

Usage
    python manage.py import_benchmark --datasets bpi2017
    python manage.py import_benchmark --datasets bpi2017 bpi2020 rtfm helpdesk \
        --cases-per-scenario 30
"""
from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.benchmark.models import Case, EventLog
from apps.benchmark.services.corpus_builder import build_corpus
from apps.benchmark.services.log_importer import SUPPORTED_LOGS, import_log
from apps.benchmark.services.process_discovery import (
    build_constraint_set,
    derive_policy_rules,
    discover_model,
    mine_declare_constraints,
)
from apps.benchmark.services.scenario_builder import build_benchmark
from apps.processes.models import Process


class Command(BaseCommand):
    help = 'Import the public event logs and build the WF-Adapt benchmark.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--datasets', nargs='+', default=['bpi2017'],
            help='Datasets to import. One or more of: '
                 + ', '.join(sorted(SUPPORTED_LOGS)),
        )
        parser.add_argument(
            '--cases-per-scenario', type=int, default=120,
            help='Benchmark cases per scenario type and dataset (default 120).',
        )
        parser.add_argument(
            '--seed', type=int, default=42,
            help='Seed of the deterministic case selection (default 42).',
        )
        parser.add_argument(
            '--max-corpus-documents', type=int, default=400,
            help='Maximum number of SOP corpus documents per process.',
        )
        parser.add_argument(
            '--skip-import', action='store_true',
            help='Rebuild the benchmark from the cases already in the database.',
        )

    def handle(self, *args, **options):
        datasets = options['datasets']
        unknown = [d for d in datasets if d not in SUPPORTED_LOGS]
        if unknown:
            raise CommandError(
                f'Unknown dataset(s): {", ".join(unknown)}. '
                f'Known datasets: {", ".join(sorted(SUPPORTED_LOGS))}'
            )

        summary = []
        for dataset in datasets:
            summary.append(self._handle_dataset(dataset, options))

        self.stdout.write(self.style.SUCCESS('\nWF-Adapt benchmark build complete:'))
        for entry in summary:
            self.stdout.write(
                f"  {entry['dataset']:<10} cases={entry['cases']:<6} "
                f"train={entry['train']:<6} test={entry['test']:<6} "
                f"benchmark={entry['benchmark_cases']:<6} "
                f"activities={entry['activities']:<4} "
                f"constraints={entry['constraints']:<5} "
                f"corpus={entry['corpus']}"
            )
        total = sum(entry['benchmark_cases'] for entry in summary)
        self.stdout.write(self.style.SUCCESS(f'  total benchmark cases: {total}'))

    def _handle_dataset(self, dataset, options):
        started = time.time()
        spec = SUPPORTED_LOGS[dataset]

        if not options['skip_import']:
            self.stdout.write(f'\n=== {dataset}: importing {spec.filename} ===')
            stats = import_log(dataset)
            self.stdout.write(
                f"  imported {stats['num_cases']} cases / "
                f"{stats['num_events']} events / "
                f"{stats['num_activities']} activities "
                f"(train {stats['train_cases']}, test {stats['test_cases']})"
            )

        event_log = EventLog.objects.get(name=dataset)
        all_cases = list(
            Case.objects.filter(event_log=event_log).order_by('case_id')
        )
        train_cases = [c for c in all_cases
                       if (c.attributes or {}).get('split') == 'train']
        test_cases = [c for c in all_cases
                      if (c.attributes or {}).get('split') == 'test']
        if not train_cases or not test_cases:
            raise CommandError(
                f'{dataset}: the import produced {len(train_cases)} training and '
                f'{len(test_cases)} test cases; both are required.'
            )

        # --- 2. control-flow model (M) ---------------------------------
        self.stdout.write(f'=== {dataset}: discovering the control-flow model ===')
        sequences = [
            [event.get('activity', '') for event in (case.prefix_trace or [])]
            for case in train_cases
        ]
        traces = [
            (activities,
             [event.get('timestamp', '') for event in (case.prefix_trace or [])])
            for activities, case in zip(sequences, train_cases)
        ]
        model_xml, activities, transitions = discover_model(traces)
        self.stdout.write(
            f'  Inductive Miner: {len(activities)} activities, '
            f'{len(transitions)} transitions'
        )

        process, _ = Process.objects.update_or_create(
            name=spec.display_name,
            defaults={
                'description':  spec.description,
                'model_type':   'petri',
                'model_xml':    model_xml,
                'activities':   activities,
                'transitions':  transitions,
                'metadata': {
                    'domain':     spec.domain,
                    'dataset':    dataset,
                    'discovery':  'inductive_miner',
                    'train_cases': len(train_cases),
                },
            },
        )

        # --- 3. constraints (D + P) -------------------------------------
        self.stdout.write(f'=== {dataset}: mining constraints ===')
        declare = mine_declare_constraints(sequences, activities)
        policy = derive_policy_rules(
            [case.prefix_trace for case in train_cases],
            [case.attributes for case in train_cases],
            activities,
        )
        constraint_set, count = build_constraint_set(
            process, f'{dataset} v1.0', declare + policy)
        self.stdout.write(
            f'  {len(declare)} Declare + {len(policy)} policy constraints'
        )

        # --- 4. corpus (K) ----------------------------------------------
        self.stdout.write(f'=== {dataset}: building the SOP corpus ===')
        corpus_size = build_corpus(
            process, event_log, train_cases,
            max_documents=options['max_corpus_documents'],
            constraint_set=constraint_set,
        )
        self.stdout.write(f'  {corpus_size} corpus documents')

        # --- 5. benchmark scenarios -------------------------------------
        self.stdout.write(f'=== {dataset}: building the benchmark ===')
        result = build_benchmark(
            process, event_log,
            cases_per_scenario=options['cases_per_scenario'],
            constraint_set=constraint_set,
            seed=options['seed'],
        )
        self.stdout.write(
            f"  {result['benchmark_cases']} benchmark cases "
            f"({result['cases_per_scenario']} per scenario)"
        )

        return {
            'dataset':         dataset,
            'cases':           len(train_cases) + len(test_cases),
            'train':           len(train_cases),
            'test':            len(test_cases),
            'benchmark_cases': result['benchmark_cases'],
            'activities':      len(activities),
            'constraints':     count,
            'corpus':          corpus_size,
            'seconds':         round(time.time() - started, 1),
        }

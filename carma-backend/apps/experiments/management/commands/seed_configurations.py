"""
Seed the B0-B7 experiment configurations from the canonical runner matrix.

    python manage.py seed_configurations [--llm claude-opus-5-5]

The matrix in ``carma_engine.runners.registry`` is the single source of truth for
the factorial design; this command mirrors it into the database so that runs
can be created against real configuration rows.
"""
from django.core.management.base import BaseCommand

from apps.experiments.models import RunConfiguration
from carma_engine.runners import RUNNER_MATRIX

NAMES = {
    'B0': 'Rule-based baseline (no LLM, no retrieval)',
    'B1': 'Single LLM (no retrieval)',
    'B2': 'Single LLM + VectorRAG',
    'B3': 'Single LLM + GraphRAG',
    'B4': 'Multi-agent + VectorRAG',
    'B5': 'Multi-agent + Constraint-Aware Retrieval (CAR)',
    'B6': 'Multi-agent + VectorRAG + Symbolic Constraint Verifier (SCV)',
    'B7': 'CARMA full (CAR + SCV + multi-agent)',
}

DESCRIPTIONS = {
    'B0': 'Deterministic rule-based adapter. Lower bound of the study.',
    'B1': 'One LLM plans the adaptation from the case description only.',
    'B2': 'B1 plus dense vector retrieval over the process corpus.',
    'B3': 'B1 plus graph-proximity retrieval over the constraint graph.',
    'B4': 'Four specialist agents with vector retrieval.',
    'B5': 'Four specialist agents with constraint-aware retrieval.',
    'B6': 'B4 plus the symbolic constraint verifier (SCV): vector retrieval, '
          'no constraint-aware retrieval.',
    'B7': 'Full CARMA: constraint-aware retrieval, multi-agent team, SCV '
          'and human escalation.',
}


class Command(BaseCommand):
    help = 'Create or update the B0-B7 run configurations from the runner matrix.'

    def add_arguments(self, parser):
        parser.add_argument('--llm', default='claude-opus-5-5',
                            help='Default LLM model for the configurations.')
        parser.add_argument('--temperature', type=float, default=0.0)
        parser.add_argument('--max-tokens', type=int, default=4096)

    def handle(self, *args, **options):
        created, updated = 0, 0

        for code, runner_class in sorted(RUNNER_MATRIX.items()):
            defaults = {
                'name': NAMES.get(code, f'Configuration {code}'),
                'description': DESCRIPTIONS.get(code, ''),
                'use_car': runner_class.retrieval_type == 'constraint_aware',
                'use_scv': runner_class.use_scv,
                'use_graph_rag': runner_class.retrieval_type == 'graph',
                'multi_agent': runner_class.multi_agent,
                'num_agents': runner_class.num_agents,
                'llm_model': options['llm'],
                'temperature': options['temperature'],
                'max_tokens': options['max_tokens'],
            }
            config, was_created = RunConfiguration.objects.update_or_create(
                code=code, defaults=defaults)
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f'created {code}: {config.name}'))
            else:
                updated += 1
                self.stdout.write(f'updated {code}: {config.name}')

        self.stdout.write(self.style.SUCCESS(
            f'Done — {created} created, {updated} updated, '
            f'{RunConfiguration.objects.count()} configurations in total.'))

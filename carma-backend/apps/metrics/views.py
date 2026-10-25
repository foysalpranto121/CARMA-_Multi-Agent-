"""CARMA — Metrics Views"""
from django.db.models import Avg, Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsResearcherOrAdmin

from .models import RunMetrics
from .serializers import RunMetricsSerializer
from .services.stats import (
    bootstrap_ci,
    friedman_test,
    mcnemar_pairwise,
    posthoc_wilcoxon,
)


class RunMetricsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = RunMetrics.objects.select_related('run').all()
    serializer_class   = RunMetricsSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['run__configuration', 'run__seed', 'scenario_code']


class StatisticalTestsView(APIView):
    """
    Statistical comparison of the configurations of an experiment.

    Query parameters (all optional, they combine as an AND filter)
      run           id of an ``ExperimentRun`` — a single (configuration, seed) run
      experiment    alias of ``run``
      configuration configuration code (``B0`` … ``B7``)
    """
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]

    def get(self, request):
        from apps.experiments.models import Adaptation

        adaptations = Adaptation.objects.select_related(
            'run__configuration', 'benchmark_case').all()
        # A run on the test double measures the plumbing, never a model.
        if request.query_params.get('include_mock') not in ('1', 'true'):
            adaptations = adaptations.exclude(llm_backend='mock')

        run_id = request.query_params.get('run') or request.query_params.get('experiment')
        if run_id:
            adaptations = adaptations.filter(run_id=run_id)
        configuration = request.query_params.get('configuration')
        if configuration:
            adaptations = adaptations.filter(run__configuration__code=configuration)

        rows = []
        latency_samples: dict[str, list] = {}
        for adaptation in adaptations.iterator():
            config_code = adaptation.run.configuration.code
            case_id = str(adaptation.benchmark_case_id)
            rows.append({
                'benchmark_case_id': case_id,
                'config_code': config_code,
                'constraint_violated': adaptation.constraint_violated,
                'task_success': adaptation.task_success,
                'latency_s': adaptation.latency_s,
            })
            if adaptation.latency_s is not None:
                latency_samples.setdefault(config_code, []).append(adaptation.latency_s)

        if not rows:
            return Response({
                'detail': 'No adaptation results available for the requested selection.',
                'n_adaptations': 0,
                'mcnemar_violation_rate': [],
                'mcnemar_task_success': [],
                'friedman_latency': {},
                'posthoc_latency': [],
                'bootstrap_latency': {},
            })

        payload = {
            'n_adaptations': len(rows),
            'mcnemar_violation_rate': mcnemar_pairwise(rows, 'constraint_violated'),
            'mcnemar_task_success': mcnemar_pairwise(rows, 'task_success'),
            'friedman_latency': friedman_test(latency_samples),
            'posthoc_latency': posthoc_wilcoxon(latency_samples),
            'bootstrap_latency': {
                config: bootstrap_ci(values)
                for config, values in latency_samples.items()
            },
        }
        return Response(payload)


class CostBreakdownView(APIView):
    """Return the ViolCost + ExecCost breakdown per configuration."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.experiments.models import RunResult

        results = RunResult.objects.all()

        configuration = request.query_params.get('configuration')
        if configuration:
            results = results.filter(run__configuration__code=configuration)
        seed = request.query_params.get('seed')
        if seed:
            results = results.filter(run__seed=seed)

        rows = (
            results
            .values('run__configuration__code')
            .annotate(
                mean_viol=Avg('mean_viol_cost'),
                mean_exec=Avg('mean_exec_cost'),
                mean_tsr =Avg('task_success_rate'),
                mean_cvr =Avg('constraint_viol_rate'),
            )
            .order_by('run__configuration__code')
        )
        return Response(list(rows))


class ScenarioBreakdownView(APIView):
    """Per-scenario metric snapshot for a run or a configuration."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        metrics = RunMetrics.objects.select_related('run__configuration').all()

        run_id = request.query_params.get('run') or request.query_params.get('experiment')
        if run_id:
            metrics = metrics.filter(run_id=run_id)
        configuration = request.query_params.get('configuration')
        if configuration:
            metrics = metrics.filter(run__configuration__code=configuration)

        rows = [{
            'config_code': m.run.configuration.code,
            'scenario_code': m.scenario_code or 'ALL',
            'tsr': m.tsr,
            'cvr': m.cvr,
            'conformance': m.conformance,
            'escalation_rate': m.escalation_rate,
            'mean_latency': m.mean_latency,
            'p95_latency': m.p95_latency,
        } for m in metrics]
        return Response(rows)

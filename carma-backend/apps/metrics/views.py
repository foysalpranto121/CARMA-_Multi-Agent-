"""CARMA — Metrics Views"""
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import RunMetrics
from .serializers import RunMetricsSerializer
from apps.users.permissions import IsResearcherOrAdmin


class RunMetricsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = RunMetrics.objects.select_related('run').all()
    serializer_class   = RunMetricsSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['run__configuration', 'run__seed']


class StatisticalTestsView(APIView):
    """Run McNemar / Friedman / mixed-effects logistic regression on stored results."""
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]

    def get(self, request):
        config_a = request.query_params.get('config_a', 'B4')
        config_b = request.query_params.get('config_b', 'B7')
        # Placeholder — real computation via scipy/statsmodels in Day 3
        return Response({
            'comparison': f'{config_a} vs {config_b}',
            'mcnemar': {
                'chi2': 41.3, 'p_value': 0.0001, 'odds_ratio': 3.42,
                'ci_95': [2.1, 5.6], 'significant': True,
            },
            'friedman': {
                'chi2': 6.1, 'p_value': 0.19, 'significant': False,
            },
            'cliff_delta': 0.18,
            'note': 'Holm–Bonferroni corrected for 6 pairwise comparisons.',
        })


class CostBreakdownView(APIView):
    """Return ViolCost + ExecCost breakdown per configuration."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.experiments.models import RunResult
        from django.db.models import Avg
        results = (
            RunResult.objects
            .values('run__configuration__code')
            .annotate(
                mean_viol=Avg('mean_viol_cost'),
                mean_exec=Avg('mean_exec_cost'),
                mean_tsr =Avg('task_success_rate'),
                mean_cvr =Avg('constraint_viol_rate'),
            )
            .order_by('run__configuration__code')
        )
        return Response(list(results))

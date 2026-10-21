"""CARMA — Experiment Views"""
import csv
import io

from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsOwnerOrAdmin, IsResearcherOrAdmin

from .models import Adaptation, ExperimentRun, RunConfiguration, RunResult
from .serializers import (
    AdaptationSerializer,
    ExperimentRunListSerializer,
    ExperimentRunSerializer,
    RunConfigurationSerializer,
    RunResultSerializer,
)

EXPORT_COLUMNS = [
    'adaptation_id', 'run_id', 'config_code', 'seed', 'case_id', 'scenario',
    'status', 'task_success', 'viol_cost', 'exec_cost', 'total_cost',
    'conformance_fitness', 'latency_s', 'repair_rounds', 'scv_approved',
    'llm_tokens',
]


class RunConfigurationViewSet(viewsets.ModelViewSet):
    queryset           = RunConfiguration.objects.all()
    serializer_class   = RunConfigurationSerializer
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['code', 'llm_model', 'use_car', 'use_scv']


class ExperimentRunViewSet(viewsets.ModelViewSet):
    queryset           = ExperimentRun.objects.select_related(
                            'configuration', 'created_by').all()
    serializer_class   = ExperimentRunSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ['status', 'configuration', 'seed']
    ordering_fields    = ['created_at', 'started_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return ExperimentRunListSerializer
        return ExperimentRunSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAuthenticated(), IsResearcherOrAdmin(), IsOwnerOrAdmin()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def matrix(self, request):
        """
        The B0-B7 configuration matrix (the factorial design of the study).
        """
        from carma_engine.runners import RUNNER_MATRIX  # noqa: PLC0415

        rows = []
        for code, runner_class in sorted(RUNNER_MATRIX.items()):
            rows.append({
                'code': code,
                'retrieval': runner_class.retrieval_type,
                'multi_agent': runner_class.multi_agent,
                'use_scv': runner_class.use_scv,
                'num_agents': runner_class.num_agents,
            })
        return Response(rows)


class RunResultViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = RunResult.objects.select_related('run').all()
    serializer_class   = RunResultSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['run', 'run__configuration', 'run__seed']


class AdaptationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = Adaptation.objects.select_related('run', 'benchmark_case').all()
    serializer_class   = AdaptationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ['run', 'status', 'task_success', 'scv_approved']
    ordering_fields    = ['created_at', 'viol_cost', 'latency_s']


# ── Action views ───────────────────────────────────────────────
class StartExperimentView(APIView):
    """Start a pending (or paused) experiment run."""
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]

    def post(self, request, pk):
        try:
            run = ExperimentRun.objects.get(pk=pk)
        except ExperimentRun.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if run.status not in ('pending', 'paused'):
            return Response({'detail': f'Cannot start a {run.status} run.'},
                            status=status.HTTP_400_BAD_REQUEST)

        from apps.experiments.tasks import run_experiment

        task = run_experiment.delay(str(run.id))
        run.celery_task_id = task.id
        run.status         = 'running'
        run.started_at     = timezone.now()
        run.save(update_fields=['celery_task_id', 'status', 'started_at'])
        return Response({'detail': 'Experiment started.', 'task_id': task.id})


class PauseExperimentView(APIView):
    """Pause a running experiment run."""
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]

    def post(self, request, pk):
        try:
            run = ExperimentRun.objects.get(pk=pk)
        except ExperimentRun.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if run.status != 'running':
            return Response({'detail': 'Only running experiments can be paused.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if run.celery_task_id:
            from celery.app.control import Control

            from config.celery import app as celery_app

            Control(celery_app).revoke(run.celery_task_id, terminate=False)
        run.status = 'paused'
        run.save(update_fields=['status'])
        return Response({'detail': 'Experiment paused.'})


class ExportResultsView(APIView):
    """Export the adaptations of a run as CSV."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            run = ExperimentRun.objects.select_related('configuration').get(pk=pk)
        except ExperimentRun.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        adaptations = Adaptation.objects.filter(run=run).select_related(
            'benchmark_case__scenario', 'benchmark_case__case')

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(EXPORT_COLUMNS)
        for adaptation in adaptations:
            writer.writerow([
                str(adaptation.id),
                str(run.id),
                run.configuration.code,
                run.seed,
                adaptation.benchmark_case.case.case_id,
                adaptation.benchmark_case.scenario.code,
                adaptation.status,
                adaptation.task_success,
                adaptation.viol_cost,
                adaptation.exec_cost,
                adaptation.total_cost,
                adaptation.conformance_fitness,
                adaptation.latency_s,
                adaptation.repair_rounds,
                adaptation.scv_approved,
                adaptation.llm_tokens,
            ])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="run_{run.id}_results.csv"'
        return response

"""CARMA — Experiment Views"""
from rest_framework import viewsets, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
import csv, io
from django.http import HttpResponse

from .models import RunConfiguration, ExperimentRun, Adaptation, RunResult
from .serializers import (
    RunConfigurationSerializer, ExperimentRunSerializer,
    ExperimentRunListSerializer, AdaptationSerializer, RunResultSerializer,
)
from apps.users.permissions import IsResearcherOrAdmin, IsOwnerOrAdmin


class RunConfigurationViewSet(viewsets.ModelViewSet):
    queryset           = RunConfiguration.objects.all()
    serializer_class   = RunConfigurationSerializer
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['code', 'llm_model', 'use_car', 'use_scv']


class ExperimentRunViewSet(viewsets.ModelViewSet):
    queryset           = ExperimentRun.objects.select_related(
                            'configuration', 'created_by').all()
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ['status', 'configuration', 'seed']
    ordering_fields    = ['created_at', 'started_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return ExperimentRunListSerializer
        return ExperimentRunSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        run = self.get_object()
        if run.status not in ('pending', 'paused'):
            return Response({'detail': f'Cannot start a {run.status} run.'}, status=400)
        from apps.experiments.tasks import run_experiment
        task = run_experiment.delay(str(run.id))
        run.celery_task_id = task.id
        run.status         = 'running'
        run.started_at     = timezone.now()
        run.save(update_fields=['celery_task_id', 'status', 'started_at'])
        return Response({'detail': 'Experiment started.', 'task_id': task.id})

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        run = self.get_object()
        if run.status != 'running':
            return Response({'detail': 'Only running experiments can be paused.'}, status=400)
        from celery.app.control import Control
        from config.celery import app as celery_app
        Control(celery_app).revoke(run.celery_task_id, terminate=False)
        run.status = 'paused'
        run.save(update_fields=['status'])
        return Response({'detail': 'Experiment paused.'})

    @action(detail=True, methods=['get'])
    def export(self, request, pk=None):
        run = self.get_object()
        adaptations = Adaptation.objects.filter(run=run).select_related('benchmark_case')
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'adaptation_id', 'case_id', 'scenario', 'status',
            'task_success', 'viol_cost', 'exec_cost', 'total_cost',
            'conformance_fitness', 'latency_s', 'repair_rounds', 'scv_approved',
        ])
        for a in adaptations:
            writer.writerow([
                str(a.id), a.benchmark_case.case.case_id,
                a.benchmark_case.scenario.code,
                a.status, a.task_success,
                a.viol_cost, a.exec_cost, a.total_cost,
                a.conformance_fitness, a.latency_s,
                a.repair_rounds, a.scv_approved,
            ])
        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="run_{run.id}_results.csv"'
        return response


class RunResultViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = RunResult.objects.select_related('run').all()
    serializer_class   = RunResultSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['run__configuration', 'run__seed']


class AdaptationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = Adaptation.objects.select_related('run', 'benchmark_case').all()
    serializer_class   = AdaptationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ['run', 'status', 'task_success', 'scv_approved']
    ordering_fields    = ['created_at', 'viol_cost', 'latency_s']


# ── Action views wired directly (no proxy needed) ──────────────
class StartExperimentView(APIView):
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]

    def post(self, request, pk):
        from .models import ExperimentRun
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
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]

    def post(self, request, pk):
        from .models import ExperimentRun
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
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from .models import ExperimentRun, Adaptation
        try:
            run = ExperimentRun.objects.get(pk=pk)
        except ExperimentRun.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        adaptations = Adaptation.objects.filter(run=run).select_related(
            'benchmark_case__scenario', 'benchmark_case__case')
        import csv, io
        from django.http import HttpResponse
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'adaptation_id', 'case_id', 'scenario', 'status',
            'task_success', 'viol_cost', 'exec_cost', 'total_cost',
            'conformance_fitness', 'latency_s', 'repair_rounds', 'scv_approved',
        ])
        for a in adaptations:
            writer.writerow([
                str(a.id),
                a.benchmark_case.case.case_id,
                a.benchmark_case.scenario.code,
                a.status, a.task_success,
                a.viol_cost, a.exec_cost, a.total_cost,
                a.conformance_fitness, a.latency_s,
                a.repair_rounds, a.scv_approved,
            ])
        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="run_{run.id}_results.csv"'
        return response


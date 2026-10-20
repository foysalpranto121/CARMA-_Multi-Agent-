"""CARMA — Benchmark Views"""
from rest_framework import viewsets, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from .models import EventLog, Case, BenchmarkScenario, BenchmarkCase
from .serializers import (
    EventLogSerializer, CaseSerializer,
    BenchmarkScenarioSerializer, BenchmarkCaseSerializer, BenchmarkCaseListSerializer,
)
from apps.users.permissions import IsResearcherOrAdmin, IsAnnotatorOrAdmin


class EventLogViewSet(viewsets.ModelViewSet):
    queryset           = EventLog.objects.all()
    serializer_class   = EventLogSerializer
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]
    filter_backends    = [filters.SearchFilter]
    search_fields      = ['name', 'display_name']


class CaseViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = Case.objects.select_related('event_log').all()
    serializer_class   = CaseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields   = ['event_log', 'current_stage']
    search_fields      = ['case_id']


class BenchmarkScenarioViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = BenchmarkScenario.objects.all()
    serializer_class   = BenchmarkScenarioSerializer
    permission_classes = [IsAuthenticated]


class BenchmarkCaseViewSet(viewsets.ModelViewSet):
    queryset           = BenchmarkCase.objects.select_related(
                            'case', 'scenario', 'process', 'constraint_set',
                            'annotator_1', 'annotator_2').all()
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields   = ['scenario', 'is_validated', 'process']
    ordering_fields    = ['created_at', 'gold_viol_cost']

    def get_serializer_class(self):
        if self.action == 'list':
            return BenchmarkCaseListSerializer
        return BenchmarkCaseSerializer

    def get_permissions(self):
        if self.action in ('update', 'partial_update', 'destroy'):
            return [IsAuthenticated(), IsAnnotatorOrAdmin()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'])
    def stats(self, request):
        from django.db.models import Count, Avg
        return Response({
            'total':      self.get_queryset().count(),
            'validated':  self.get_queryset().filter(is_validated=True).count(),
            'by_scenario': list(
                self.get_queryset().values('scenario__code')
                    .annotate(count=Count('id'), mean_kappa=Avg('kappa'))
                    .order_by('scenario__code')
            ),
        })


class ImportLogView(APIView):
    """Import a BPI XES log and extract cases."""
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]

    def post(self, request):
        # Dispatch async import task
        from apps.benchmark.tasks import import_event_log
        log_name = request.data.get('log_name')
        file     = request.FILES.get('file')
        if not log_name:
            return Response({'detail': 'log_name required.'}, status=400)
        task = import_event_log.delay(log_name, str(file) if file else None)
        return Response({'task_id': task.id, 'detail': 'Import started.'}, status=202)

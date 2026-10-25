"""CARMA — Benchmark Views"""
from django.core.files.storage import default_storage
from django.db.models import Avg, Count
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsAnnotatorOrAdmin, IsResearcherOrAdmin

from apps.metrics.services.stats import cohen_kappa

from .models import BenchmarkCase, BenchmarkScenario, Case, EventLog, GoldAnnotation
from .serializers import (
    BenchmarkCaseListSerializer,
    BenchmarkCaseSerializer,
    BenchmarkScenarioSerializer,
    CaseSerializer,
    EventLogSerializer,
    GoldAnnotationSerializer,
)


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
        if self.action == 'annotations' and self.request.method == 'POST':
            return [IsAuthenticated(), IsAnnotatorOrAdmin()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['get', 'post'])
    def annotations(self, request, pk=None):
        """
        The annotations of a case.  ``POST`` records (or revises) the
        requesting annotator's own reading of the reference.
        """
        benchmark_case = self.get_object()
        if request.method == 'POST':
            serializer = GoldAnnotationSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            annotation, _ = GoldAnnotation.objects.update_or_create(
                benchmark_case=benchmark_case, annotator=request.user,
                defaults=serializer.validated_data)
            _record_annotators(benchmark_case)
            return Response(GoldAnnotationSerializer(annotation).data,
                            status=status.HTTP_201_CREATED)
        rows = benchmark_case.annotations.select_related('annotator')
        return Response(GoldAnnotationSerializer(rows, many=True).data)

    @action(detail=False, methods=['get'])
    def agreement(self, request):
        """
        Cohen's κ of the first two annotators over the strategy labels of the
        cases both annotated (filter with ``?scenario=`` / ``?process=``).
        """
        queryset = self.filter_queryset(self.get_queryset()).prefetch_related('annotations')
        labels_a, labels_b, disagreements, annotated = [], [], [], 0
        for benchmark_case in queryset:
            annotations = list(benchmark_case.annotations.all())
            if annotations:
                annotated += 1
            if len(annotations) < 2:
                continue
            first, second = annotations[0], annotations[1]
            labels_a.append(first.strategy)
            labels_b.append(second.strategy)
            if first.strategy != second.strategy:
                disagreements.append(str(benchmark_case.id))

        result = cohen_kappa(labels_a, labels_b)
        result.update({
            'annotated':        annotated,
            'double_annotated': len(labels_a),
            'disagreements':    disagreements,
        })
        return Response(result)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        return Response({
            'total':      self.get_queryset().count(),
            'validated':  self.get_queryset().filter(is_validated=True).count(),
            'by_scenario': list(
                self.get_queryset().values('scenario__code')
                    .annotate(count=Count('id'), mean_kappa=Avg('kappa'))
                    .order_by('scenario__code')
            ),
        })


def _record_annotators(benchmark_case):
    """Keep the case's two annotator slots in step with its first two annotations."""
    annotators = [annotation.annotator
                  for annotation in benchmark_case.annotations.select_related('annotator')[:2]]
    benchmark_case.annotator_1 = annotators[0] if annotators else None
    benchmark_case.annotator_2 = annotators[1] if len(annotators) > 1 else None
    benchmark_case.save(update_fields=['annotator_1', 'annotator_2'])


class ImportLogView(APIView):
    """
    Import a BPI XES event log and extract its cases.

    The XES file is either uploaded with the request (multipart) or already
    present in the media storage under ``file_path``.
    """
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]

    def post(self, request):
        from apps.benchmark.tasks import import_event_log

        log_name = request.data.get('log_name')
        if not log_name:
            return Response({'detail': 'log_name is required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        storage_path = None
        uploaded = request.FILES.get('file')
        if uploaded is not None:
            storage_path = default_storage.save(f'event_logs/{uploaded.name}', uploaded)
        elif request.data.get('file_path'):
            storage_path = request.data['file_path']

        task = import_event_log.delay(log_name, None, storage_path)
        return Response({'task_id': task.id, 'detail': 'Import started.'},
                        status=status.HTTP_202_ACCEPTED)

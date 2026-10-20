"""CARMA — Processes Views"""
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema_view, extend_schema
from .models import Process, ConstraintSet, Constraint, CorpusDocument
from .serializers import (
    ProcessSerializer, ConstraintSetSerializer,
    ConstraintSerializer, CorpusDocumentSerializer,
)
from apps.users.permissions import IsResearcherOrAdmin, IsOwnerOrAdmin


@extend_schema_view(
    list=extend_schema(summary='List processes', tags=['Processes']),
    create=extend_schema(summary='Create process', tags=['Processes']),
    retrieve=extend_schema(summary='Get process', tags=['Processes']),
    update=extend_schema(summary='Update process', tags=['Processes']),
    destroy=extend_schema(summary='Delete process', tags=['Processes']),
)
class ProcessViewSet(viewsets.ModelViewSet):
    queryset           = Process.objects.select_related('created_by').prefetch_related('constraint_sets')
    serializer_class   = ProcessSerializer
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields   = ['model_type']
    search_fields      = ['name', 'description']
    ordering_fields    = ['created_at', 'name']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ConstraintSetViewSet(viewsets.ModelViewSet):
    queryset           = ConstraintSet.objects.select_related('process')
    serializer_class   = ConstraintSetSerializer
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]
    filterset_fields   = ['process', 'is_active']


class ConstraintViewSet(viewsets.ModelViewSet):
    queryset           = Constraint.objects.select_related('constraint_set')
    serializer_class   = ConstraintSerializer
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]
    filterset_fields   = ['constraint_set', 'constraint_type']


class CorpusDocumentViewSet(viewsets.ModelViewSet):
    queryset           = CorpusDocument.objects.select_related('process')
    serializer_class   = CorpusDocumentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields   = ['process', 'doc_type', 'stage']
    search_fields      = ['title', 'content']

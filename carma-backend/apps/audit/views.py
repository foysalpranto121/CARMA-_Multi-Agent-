"""CARMA — Audit Views"""
from rest_framework import viewsets, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import AuditLogEntry
from .serializers import AuditLogEntrySerializer
from apps.users.permissions import IsResearcherOrAdmin


class AuditLogEntryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = AuditLogEntry.objects.select_related('actor_user').all()
    serializer_class   = AuditLogEntrySerializer
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ['entry_type', 'run_id', 'adaptation_id']
    ordering_fields    = ['sequence_num', 'timestamp']


class VerifyChainView(APIView):
    """Verify SHA-256 hash chain integrity."""
    permission_classes = [IsAuthenticated, IsResearcherOrAdmin]

    def get(self, request):
        run_id   = request.query_params.get('run_id')
        is_valid, broken_at = AuditLogEntry.verify_chain(run_id=run_id)
        return Response({
            'valid':      is_valid,
            'broken_at':  broken_at,
            'message':    'Chain intact.' if is_valid else f'Chain broken at sequence #{broken_at}.',
        })


class ReplayView(APIView):
    """Replay all audit entries for a given adaptation."""
    permission_classes = [IsAuthenticated]

    def get(self, request, adaptation_id):
        entries = AuditLogEntry.objects.filter(
            adaptation_id=adaptation_id).order_by('sequence_num')
        serializer = AuditLogEntrySerializer(entries, many=True)
        return Response({
            'adaptation_id': str(adaptation_id),
            'entry_count':   entries.count(),
            'entries':       serializer.data,
        })

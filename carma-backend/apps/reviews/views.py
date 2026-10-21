"""CARMA — Reviews Views"""
from rest_framework import viewsets, filters
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from .models import Escalation, HumanReview
from .serializers import EscalationSerializer, HumanReviewSerializer
from apps.users.permissions import IsReviewerOrAdmin


class EscalationViewSet(viewsets.ModelViewSet):
    queryset           = Escalation.objects.select_related(
                            'adaptation', 'assigned_to').all()
    serializer_class   = EscalationSerializer
    permission_classes = [IsAuthenticated, IsReviewerOrAdmin]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ['status', 'reason', 'priority']
    ordering_fields    = ['priority', 'created_at']

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        escalation = self.get_object()
        escalation.assigned_to = request.user
        escalation.status      = 'assigned'
        escalation.save(update_fields=['assigned_to', 'status'])
        return Response({'detail': 'Assigned to you.'})


class HumanReviewViewSet(viewsets.ModelViewSet):
    queryset           = HumanReview.objects.select_related(
                            'escalation', 'reviewer').all()
    serializer_class   = HumanReviewSerializer
    permission_classes = [IsAuthenticated, IsReviewerOrAdmin]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['decision', 'reviewer']

    def perform_create(self, serializer):
        review = serializer.save(reviewer=self.request.user)
        # Mark escalation as resolved
        review.escalation.status = 'resolved'
        review.escalation.save(update_fields=['status'])

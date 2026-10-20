"""CARMA — Escalation & Human Review Models"""
import uuid
from django.db import models
from django.conf import settings
from apps.experiments.models import Adaptation


class Escalation(models.Model):
    REASON_CHOICES = [
        ('low_confidence',   'Low Planner Confidence (< τ)'),
        ('scv_violation',    'SCV Constraint Violation'),
        ('repair_exhausted', 'Max Repair Rounds Exhausted'),
        ('conflicting_plans','Conflicting Agent Plans'),
        ('policy_breach',    'Policy Breach Detected'),
        ('manual',           'Manually Escalated'),
    ]
    STATUS_CHOICES = [
        ('pending',  'Pending Review'),
        ('assigned', 'Assigned'),
        ('resolved', 'Resolved'),
        ('rejected', 'Rejected'),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    adaptation  = models.OneToOneField(Adaptation, on_delete=models.CASCADE,
                                       related_name='escalation')
    reason      = models.CharField(max_length=25, choices=REASON_CHOICES)
    reason_detail = models.TextField(blank=True)
    confidence  = models.FloatField(null=True, blank=True)
    viol_cost   = models.FloatField(default=0.0)

    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='assigned_escalations')
    priority    = models.PositiveSmallIntegerField(default=2, help_text='1=high, 2=medium, 3=low')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'escalations'
        ordering = ['priority', '-created_at']
        indexes  = [
            models.Index(fields=['status', 'priority']),
        ]


class HumanReview(models.Model):
    DECISION_CHOICES = [
        ('approved',  'Approved as-is'),
        ('modified',  'Approved with modification'),
        ('rejected',  'Rejected — restart'),
        ('deferred',  'Deferred for later'),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    escalation  = models.OneToOneField(Escalation, on_delete=models.CASCADE,
                                       related_name='review')
    reviewer    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name='reviews')
    decision    = models.CharField(max_length=10, choices=DECISION_CHOICES)
    modified_adaptation = models.JSONField(null=True, blank=True,
                              help_text='Reviewer-corrected adaptation (if modified)')
    justification = models.TextField(blank=True)
    review_duration_s = models.FloatField(null=True, blank=True)
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'human_reviews'
        ordering = ['-reviewed_at']

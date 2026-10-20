"""CARMA — Metrics Models"""
import uuid
from django.db import models
from apps.experiments.models import ExperimentRun


class RunMetrics(models.Model):
    """Per-scenario + per-configuration metric snapshot (flattened for fast queries)."""
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run          = models.ForeignKey(ExperimentRun, on_delete=models.CASCADE,
                                     related_name='metrics')
    scenario_code= models.CharField(max_length=2, blank=True, help_text='S0–S6 or empty for overall')
    tsr          = models.FloatField(null=True, help_text='Task Success Rate')
    cvr          = models.FloatField(null=True, help_text='Constraint Violation Rate')
    conformance  = models.FloatField(null=True, help_text='Conformance Fitness')
    escalation_rate = models.FloatField(null=True)
    mean_latency = models.FloatField(null=True)
    p95_latency  = models.FloatField(null=True)
    precision_at_k   = models.FloatField(null=True)
    stage_accuracy   = models.FloatField(null=True)
    computed_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = 'run_metrics'
        unique_together = [('run', 'scenario_code')]
        ordering        = ['run', 'scenario_code']

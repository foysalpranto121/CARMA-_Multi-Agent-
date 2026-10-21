"""
CARMA — Benchmark Models (WF-Adapt Benchmark)
840 cases across 7 scenario types (S0–S6) over 4 BPI event logs.
"""
import uuid
from django.db import models
from django.conf import settings
from apps.processes.models import Process, ConstraintSet


class EventLog(models.Model):
    """Public BPI event log (XES format)."""
    LOG_CHOICES = [
        ('bpi2017', 'BPI Challenge 2017'),
        ('bpi2019', 'BPI Challenge 2019'),
        ('bpi2020', 'BPI Challenge 2020'),
        ('rtfm',    'Road Traffic Fine Management'),
    ]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name         = models.CharField(max_length=100, choices=LOG_CHOICES, unique=True)
    display_name = models.CharField(max_length=255)
    description  = models.TextField(blank=True)
    num_traces   = models.PositiveIntegerField(default=0)
    num_events   = models.PositiveIntegerField(default=0)
    xes_file     = models.FileField(upload_to='event_logs/', null=True, blank=True)
    activities   = models.JSONField(default=list)
    metadata     = models.JSONField(default=dict)
    imported_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'event_logs'

    def __str__(self):
        return self.display_name


class Case(models.Model):
    """A single process instance / trace from an event log."""
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_log   = models.ForeignKey(EventLog, on_delete=models.CASCADE, related_name='cases')
    case_id     = models.CharField(max_length=100)
    prefix_trace= models.JSONField(help_text='List of {activity, timestamp, attributes} dicts')
    attributes  = models.JSONField(default=dict, help_text='Case-level attributes')
    current_stage = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'cases'
        unique_together = [('event_log', 'case_id')]

    def __str__(self):
        return f'{self.event_log.name}::{self.case_id}'


class BenchmarkScenario(models.Model):
    """One of 7 perturbation scenario types (S0–S6)."""
    SCENARIO_CHOICES = [
        ('S0', 'Nominal'),
        ('S1', 'Exception'),
        ('S2', 'Rule Change'),
        ('S3', 'Structural Drift'),
        ('S4', 'Ambiguous Input'),
        ('S5', 'Conflicting Intents'),
        ('S6', 'Adversarial'),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code        = models.CharField(max_length=2, choices=SCENARIO_CHOICES, unique=True)
    name        = models.CharField(max_length=100)
    description = models.TextField()
    perturbation_template = models.JSONField(
        default=dict,
        help_text='Template for injecting this perturbation into a case'
    )

    class Meta:
        db_table = 'benchmark_scenarios'
        ordering = ['code']

    def __str__(self):
        return f'{self.code}: {self.name}'


class BenchmarkCase(models.Model):
    """
    One annotated WF-Adapt benchmark entry.
    Links a case × scenario × gold adaptation.
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case        = models.ForeignKey(Case, on_delete=models.CASCADE,
                                    related_name='benchmark_cases')
    scenario    = models.ForeignKey(BenchmarkScenario, on_delete=models.CASCADE,
                                    related_name='benchmark_cases')
    process     = models.ForeignKey(Process, on_delete=models.CASCADE,
                                    related_name='benchmark_cases')
    constraint_set = models.ForeignKey(ConstraintSet, on_delete=models.SET_NULL,
                                       null=True, related_name='benchmark_cases')

    # Perturbation injected for this benchmark case
    perturbation     = models.JSONField(help_text='Perturbation event e')
    perturbation_text= models.TextField(blank=True, help_text='Natural language description')

    # The executed part of the case: the prefix that has already happened
    # when the perturbation arrives.  The agent has to produce the
    # continuation of this prefix.
    prefix_trace     = models.JSONField(
        default=list,
        help_text='Executed prefix of the case (list of {activity, timestamp, ...})',
    )

    # Gold standard annotation
    gold_adaptation  = models.JSONField(help_text='Annotated correct adaptation A*')
    gold_activity_seq= models.JSONField(default=list, help_text='Gold activity sequence')
    gold_continuation= models.JSONField(
        default=list,
        help_text='The continuation the log actually recorded for this case',
    )
    gold_viol_cost   = models.FloatField(default=0.0, help_text='Gold violation cost')
    gold_exec_cost   = models.FloatField(default=0.0, help_text='Gold execution cost')

    # Inter-annotator agreement
    annotator_1    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                       related_name='annotated_cases_1')
    annotator_2    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                       related_name='annotated_cases_2')
    kappa          = models.FloatField(null=True, blank=True,
                                       help_text="Cohen's κ for this case")
    annotation_notes = models.TextField(blank=True)

    # The automated check of the reference behaviour.  It verifies that the
    # gold really belongs to the case: that the prefix is a prefix of the
    # observed trace, that the reference path is made of declared
    # activities and that the reference behaviour can be scored.
    validation_report = models.JSONField(
        default=dict, blank=True,
        help_text='Outcome of the automated validation of the gold',
    )

    is_validated   = models.BooleanField(default=False)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'benchmark_cases'
        unique_together = [('case', 'scenario')]
        indexes = [
            models.Index(fields=['scenario', 'is_validated']),
            models.Index(fields=['process']),
        ]

    def __str__(self):
        return f'BC:{self.id} [{self.scenario.code}] {self.case}'

    @property
    def executed_prefix(self) -> list:
        """
        The prefix that has already been executed when the perturbation
        arrives.  Falls back to the full trace of the underlying case for
        benchmark rows created before the prefix was split out.
        """
        if self.prefix_trace:
            return self.prefix_trace
        return self.case.prefix_trace or []

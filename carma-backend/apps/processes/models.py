"""
CARMA — Process Frame Models
Process frames F = (M, D, P)
  M: procedural model (BPMN / Petri net)
  D: declarative constraints (Declare / LTLf)
  P: policy, authority, data and temporal rules
"""
import uuid
from django.db import models
from django.conf import settings


class Process(models.Model):
    """A business process with its procedural model."""
    MODEL_TYPES = [
        ('bpmn',    'BPMN 2.0'),
        ('petri',   'Petri Net'),
        ('declare', 'Declare'),
        ('ltlf',    'LTLf'),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name        = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    model_type  = models.CharField(max_length=10, choices=MODEL_TYPES, default='bpmn')
    model_xml   = models.TextField(blank=True, help_text='BPMN/Petri XML or Declare text')
    activities  = models.JSONField(default=list,  help_text='List of activity names')
    transitions = models.JSONField(default=list,  help_text='List of {from, to, label} dicts')
    metadata    = models.JSONField(default=dict)

    created_by  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                    related_name='processes')
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'processes'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.model_type})'


class ConstraintSet(models.Model):
    """Declarative constraint set D for a process."""
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    process    = models.ForeignKey(Process, on_delete=models.CASCADE,
                                   related_name='constraint_sets')
    name       = models.CharField(max_length=255)
    version    = models.CharField(max_length=20, default='1.0')
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'constraint_sets'

    def __str__(self):
        return f'{self.name} v{self.version}'


class Constraint(models.Model):
    """An individual Declare / LTLf / policy constraint."""
    CONSTRAINT_TYPES = [
        # Declare
        ('response',         'Response A→B'),
        ('precedence',       'Precedence A<B'),
        ('succession',       'Succession A↔B'),
        ('not_coexistence',  'Not-CoExistence'),
        ('existence',        'Existence A'),
        ('absence',          'Absence A'),
        ('exactly',          'Exactly N(A)'),
        ('init',             'Init A'),
        # Policy
        ('role_required',    'Role Required'),
        ('amount_limit',     'Amount Limit'),
        ('temporal_window',  'Temporal Window'),
        # LTLf
        ('ltlf_formula',     'LTLf Formula'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    constraint_set  = models.ForeignKey(ConstraintSet, on_delete=models.CASCADE,
                                        related_name='constraints')
    constraint_type = models.CharField(max_length=30, choices=CONSTRAINT_TYPES)
    activity_a      = models.CharField(max_length=255, blank=True)
    activity_b      = models.CharField(max_length=255, blank=True)
    parameters      = models.JSONField(default=dict, help_text='Type-specific params')
    violation_cost  = models.FloatField(default=1.0, help_text='Cost weight λ_i')
    ltlf_formula    = models.TextField(blank=True)
    description     = models.TextField(blank=True)

    class Meta:
        db_table = 'constraints'

    def __str__(self):
        return f'{self.constraint_type}({self.activity_a}, {self.activity_b})'


class CorpusDocument(models.Model):
    """Knowledge corpus K — SOPs, policies, historical cases."""
    DOC_TYPES = [
        ('sop',     'Standard Operating Procedure'),
        ('policy',  'Policy Document'),
        ('case',    'Historical Case'),
        ('manual',  'Process Manual'),
        ('rule',    'Regulatory Rule'),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    process     = models.ForeignKey(Process, on_delete=models.CASCADE,
                                    related_name='corpus_docs', null=True, blank=True)
    title       = models.CharField(max_length=500)
    doc_type    = models.CharField(max_length=10, choices=DOC_TYPES)
    content     = models.TextField()
    stage       = models.CharField(max_length=255, blank=True,
                                   help_text='Process stage this doc is relevant to')
    timestamp   = models.DateTimeField(null=True, blank=True,
                                       help_text='Document effective date')
    qdrant_id   = models.CharField(max_length=100, blank=True,
                                   help_text='Qdrant point ID for vector retrieval')
    embedding_model = models.CharField(max_length=100, default='BAAI/bge-base-en-v1.5')
    metadata    = models.JSONField(default=dict)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'corpus_documents'
        indexes  = [models.Index(fields=['process', 'doc_type', 'stage'])]

    def __str__(self):
        return f'[{self.doc_type}] {self.title[:60]}'

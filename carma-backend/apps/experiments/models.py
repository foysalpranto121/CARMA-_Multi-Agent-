"""
CARMA — Experiment Models
8 configurations (B0-B7) × 3 LLMs × 3 seeds = 72 runs × 840 cases = 60,480 tasks.
"""
import uuid
from django.db import models
from django.conf import settings
from apps.processes.models import Process, ConstraintSet
from apps.benchmark.models import BenchmarkCase


class RunConfiguration(models.Model):
    """
    One of 8 experiment configurations B0–B7.
    B7 = CARMA full (CAR=True, SCV=True, multi_agent=True, agents=4)
    """
    CONFIG_CODES = [(f'B{i}', f'B{i}') for i in range(8)]
    MODEL_CHOICES = [
        ('claude-opus-5-5',   'Claude Opus 5.5 (Frontier)'),
        ('claude-sonnet-5-5', 'Claude Sonnet 5.5'),
        ('claude-haiku-5-5',  'Claude Haiku 5.5'),
        ('openai/gpt-oss-120b', 'gpt-oss 120B (open-weight, Groq free tier)'),
        ('openai/gpt-oss-20b',  'gpt-oss 20B (open-weight, Groq free tier)'),
        ('qwen/qwen3.8-27b',    'Qwen 3.8 27B (open-weight, Groq free tier)'),
        ('gpt-4o',          'GPT-4o'),
        ('gpt-4o-mini',     'GPT-4o-mini'),
        ('llama3.1-70b',    'Llama 3.1 70B'),
        ('llama3.1-8b',     'Llama 3.1 8B'),
        ('mistral-7b',      'Mistral 7B'),
        ('qwen2.5-32b',     'Qwen 2.5 32B'),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code        = models.CharField(max_length=2, choices=CONFIG_CODES)
    name        = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Component switches
    use_car         = models.BooleanField(default=False, help_text='Constraint-Aware Retriever on')
    use_scv         = models.BooleanField(default=False, help_text='Symbolic Constraint Verifier on')
    use_graph_rag   = models.BooleanField(default=False, help_text='GraphRAG instead of VecRAG')
    multi_agent     = models.BooleanField(default=False, help_text='Multi-agent vs single LLM')
    num_agents      = models.PositiveSmallIntegerField(default=1)

    # LLM settings
    llm_model       = models.CharField(max_length=50, choices=MODEL_CHOICES, default='claude-opus-5-5')
    temperature     = models.FloatField(default=0.0)
    max_tokens      = models.PositiveIntegerField(default=4096)
    reasoning_effort = models.CharField(
        max_length=10, blank=True, default='',
        choices=[('', 'provider default'), ('low', 'low'), ('medium', 'medium'), ('high', 'high')],
        help_text='Reasoning effort of a reasoning model (gpt-oss); empty = provider default')

    # CAR retriever params (if use_car=True)
    top_k           = models.PositiveSmallIntegerField(default=10)
    alpha           = models.FloatField(default=0.6, help_text='Similarity weight α')
    beta            = models.FloatField(default=0.2, help_text='Proximity weight β')
    gamma           = models.FloatField(default=0.2, help_text='Stage-match weight γ')

    # Agent behaviour
    k_repair_rounds = models.PositiveSmallIntegerField(
        default=3, help_text='Maximum planner repair rounds before escalation')
    tau_threshold   = models.FloatField(
        default=0.5, help_text='Confidence threshold τ for human escalation')

    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'run_configurations'
        ordering = ['code']

    def __str__(self):
        return f'{self.code}: {self.name}'


class ExperimentRun(models.Model):
    """
    A full experiment run across all benchmark cases for one configuration + seed.
    """
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('running',   'Running'),
        ('paused',    'Paused'),
        ('completed', 'Completed'),
        ('failed',    'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration= models.ForeignKey(RunConfiguration, on_delete=models.CASCADE,
                                     related_name='runs')
    process      = models.ForeignKey(Process, on_delete=models.CASCADE,
                                     related_name='runs', null=True, blank=True)
    constraint_set = models.ForeignKey(ConstraintSet, on_delete=models.SET_NULL,
                                       null=True, blank=True)

    seed         = models.PositiveSmallIntegerField(default=42,
                       help_text='Random seed for reproducibility')
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    celery_task_id = models.CharField(max_length=255, blank=True)

    # Progress
    total_cases     = models.PositiveIntegerField(default=0)
    completed_cases = models.PositiveIntegerField(default=0)
    failed_cases    = models.PositiveIntegerField(default=0)

    # Timing
    started_at   = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    estimated_duration_s = models.FloatField(null=True, blank=True)

    created_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                     related_name='experiment_runs')
    created_at   = models.DateTimeField(auto_now_add=True)
    error_log    = models.TextField(blank=True)

    class Meta:
        db_table = 'experiment_runs'
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['status']),
            models.Index(fields=['configuration', 'seed']),
        ]

    def __str__(self):
        return f'Run:{self.id} [{self.configuration.code}] seed={self.seed} — {self.status}'

    @property
    def progress_pct(self):
        if not self.total_cases:
            return 0
        return round(self.completed_cases / self.total_cases * 100, 1)


class Adaptation(models.Model):
    """
    A single agent-produced adaptation for one benchmark case in one run.
    σ·A must satisfy F or escalate.
    """
    STATUS_CHOICES = [
        ('success',   'Success'),
        ('violation', 'Violation'),
        ('escalated', 'Escalated'),
        ('repair',    'Repair'),
        ('blocked',   'Blocked by the SCV'),
        ('declined',  'Declined to act'),
        ('failed',    'Failed'),
    ]

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run           = models.ForeignKey(ExperimentRun, on_delete=models.CASCADE,
                                      related_name='adaptations')
    benchmark_case= models.ForeignKey(BenchmarkCase, on_delete=models.CASCADE,
                                      related_name='adaptations')

    # Agent output
    plan_id       = models.CharField(max_length=64, blank=True)
    adaptation    = models.JSONField(help_text='Produced adaptation A')
    activity_seq  = models.JSONField(default=list)
    confidence    = models.FloatField(null=True, blank=True)

    # Verification results
    scv_approved  = models.BooleanField(null=True, blank=True)
    scv_token     = models.CharField(max_length=255, blank=True)
    viol_cost     = models.FloatField(default=0.0)
    exec_cost     = models.FloatField(default=0.0)
    total_cost    = models.FloatField(default=0.0)

    # CAR retrieval
    retrieved_docs = models.JSONField(default=list,
                        help_text='[{doc_id, score, provenance_id}] list')
    retrieval_scores = models.JSONField(default=dict)

    # Metrics — scored against the gold by carma_engine.scoring
    task_success  = models.BooleanField(null=True, blank=True,
                        help_text='Goal reached with no hard violation')
    goal_reached  = models.BooleanField(null=True, blank=True)
    gold_exact_match = models.BooleanField(null=True, blank=True,
                        help_text='Executed sequence equals the gold sequence')
    gold_similarity  = models.FloatField(null=True, blank=True,
                        help_text='2·LCS similarity of the executed and the gold sequence')
    hard_violation   = models.BooleanField(null=True, blank=True,
                        help_text='The executed trace violates a hard constraint')
    unsafe_action    = models.BooleanField(null=True, blank=True,
                        help_text='A violating write action was executed')
    conformance_fitness = models.FloatField(null=True, blank=True)
    repair_rounds = models.PositiveSmallIntegerField(default=0)

    # Provenance of the adaptation
    planned_seq   = models.JSONField(default=list, blank=True,
                        help_text='Activities the agent proposed (activity_seq is what ran)')
    plan_source   = models.CharField(max_length=20, blank=True,
                        help_text='llm | unparseable | error | heuristic | rule_based')
    llm_backend   = models.CharField(max_length=20, blank=True,
                        help_text='anthropic | openai | ollama | mock | rule_based')
    served_by     = models.JSONField(default=dict, blank=True,
                        help_text='Model id -> calls it served (shows refusal fallbacks)')
    llm_calls     = models.PositiveIntegerField(default=0)
    usd_cost      = models.FloatField(null=True, blank=True, help_text='List-price cost of the case')
    error         = models.TextField(blank=True)

    status        = models.CharField(max_length=10, choices=STATUS_CHOICES, default='failed')
    latency_s     = models.FloatField(null=True, blank=True, help_text='End-to-end latency in seconds')
    llm_tokens    = models.PositiveIntegerField(default=0)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'adaptations'
        indexes  = [
            models.Index(fields=['run', 'status']),
            models.Index(fields=['benchmark_case']),
        ]

    def __str__(self):
        return f'Adaptation:{self.id} [{self.status}]'

    @property
    def constraint_violated(self) -> bool:
        """
        The CVR outcome: the executed trace violates a hard constraint.

        Rows recorded before ``hard_violation`` existed fall back to "any
        violation cost".
        """
        if self.hard_violation is not None:
            return self.hard_violation
        return bool(self.viol_cost and self.viol_cost > 0)


class RunResult(models.Model):
    """Aggregated results for a completed ExperimentRun."""
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run         = models.OneToOneField(ExperimentRun, on_delete=models.CASCADE,
                                       related_name='result')
    # Core metrics (means)
    task_success_rate    = models.FloatField(null=True)
    constraint_viol_rate = models.FloatField(null=True)
    conformance_fitness  = models.FloatField(null=True)
    escalation_rate      = models.FloatField(null=True)
    repair_rate          = models.FloatField(null=True)
    mean_viol_cost       = models.FloatField(null=True)
    mean_exec_cost       = models.FloatField(null=True)
    mean_latency_s       = models.FloatField(null=True)
    p95_latency_s        = models.FloatField(null=True)
    total_llm_tokens     = models.PositiveIntegerField(default=0)

    # Per-scenario breakdown
    per_scenario_metrics = models.JSONField(default=dict)

    # CAR retrieval metrics (if use_car=True)
    retrieval_precision_at_k = models.FloatField(null=True)
    stage_accuracy           = models.FloatField(null=True)
    macro_f1                 = models.FloatField(null=True)

    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'run_results'

    def __str__(self):
        return f'Result for {self.run}'

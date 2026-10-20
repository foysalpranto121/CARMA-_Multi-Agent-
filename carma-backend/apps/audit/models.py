"""
CARMA — Audit Log Models
Hash-chained, tamper-evident audit log for all agent actions.
"""
import uuid
import hashlib
import json
from django.db import models
from django.conf import settings


class AuditLogEntry(models.Model):
    """
    Single entry in the hash-chained audit log.
    entry_hash = SHA-256(prev_hash ‖ entry_content)
    Enables tamper detection: any modification breaks the chain.
    """
    ENTRY_TYPES = [
        ('retrieval',  'CAR Retrieval'),
        ('plan',       'Agent Plan'),
        ('scv_check',  'SCV Verification'),
        ('action',     'Executor Action'),
        ('repair',     'Repair Attempt'),
        ('escalation', 'Escalation'),
        ('review',     'Human Review'),
        ('system',     'System Event'),
    ]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Chain links
    sequence_num = models.PositiveBigIntegerField(db_index=True)
    prev_hash    = models.CharField(max_length=64, default='0' * 64)
    entry_hash   = models.CharField(max_length=64, blank=True)

    # What happened
    entry_type   = models.CharField(max_length=15, choices=ENTRY_TYPES)
    run_id       = models.UUIDField(null=True, blank=True, db_index=True)
    adaptation_id= models.UUIDField(null=True, blank=True, db_index=True)
    case_id      = models.CharField(max_length=100, blank=True)

    # Content (stored as JSON)
    payload      = models.JSONField(default=dict,
                       help_text='Entry-type-specific data (plan, token, retrieved docs, etc.)')

    # Actor
    actor_user   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='audit_entries')
    actor_agent  = models.CharField(max_length=50, blank=True,
                                    help_text='Agent name (planner, executor, etc.)')

    timestamp    = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'audit_log_entries'
        ordering = ['sequence_num']
        indexes  = [
            models.Index(fields=['run_id', 'sequence_num']),
            models.Index(fields=['entry_type']),
        ]
        # Prevent accidental update/delete
        # (enforce at DB level with a trigger in migration)

    def __str__(self):
        return f'#{self.sequence_num} [{self.entry_type}] {self.timestamp}'

    def compute_hash(self):
        """SHA-256(prev_hash ‖ sequence_num ‖ entry_type ‖ payload ‖ timestamp)"""
        content = (
            self.prev_hash
            + str(self.sequence_num)
            + self.entry_type
            + json.dumps(self.payload, sort_keys=True, default=str)
            + str(self.timestamp)
        )
        return hashlib.sha256(content.encode()).hexdigest()

    def save(self, *args, **kwargs):
        if not self.entry_hash:
            self.entry_hash = self.compute_hash()
        super().save(*args, **kwargs)

    @classmethod
    def verify_chain(cls, run_id=None):
        """
        Verify the integrity of the audit chain.
        Returns (is_valid: bool, first_broken_seq: int | None)
        """
        qs = cls.objects.all().order_by('sequence_num')
        if run_id:
            qs = qs.filter(run_id=run_id)

        prev_hash = '0' * 64
        for entry in qs:
            # Recompute
            content = (
                prev_hash
                + str(entry.sequence_num)
                + entry.entry_type
                + json.dumps(entry.payload, sort_keys=True, default=str)
                + str(entry.timestamp)
            )
            expected = hashlib.sha256(content.encode()).hexdigest()
            if expected != entry.entry_hash:
                return False, entry.sequence_num
            prev_hash = entry.entry_hash
        return True, None

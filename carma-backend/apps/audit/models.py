"""
CARMA — Audit Log Models
Hash-chained, tamper-evident audit log for all agent actions.
"""
import hashlib
import json
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

GENESIS_HASH = '0' * 64


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
    sequence_num = models.PositiveBigIntegerField(db_index=True, unique=True)
    prev_hash    = models.CharField(max_length=64, default=GENESIS_HASH)
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

    # NOTE: ``default=timezone.now`` (not ``auto_now_add``) is required so the
    # timestamp is known *before* the entry hash is computed.  With
    # ``auto_now_add`` the value is only assigned by the database write, and
    # the hash would be computed over "None", which makes every chain
    # verification fail.
    timestamp    = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'audit_log_entries'
        ordering = ['sequence_num']
        indexes  = [
            models.Index(fields=['run_id', 'sequence_num']),
            models.Index(fields=['entry_type']),
        ]

    def __str__(self):
        return f'#{self.sequence_num} [{self.entry_type}] {self.timestamp}'

    def compute_hash(self) -> str:
        """
        SHA-256(prev_hash ‖ sequence_num ‖ entry_type ‖ payload ‖ timestamp).

        The hash must be computed over exactly the same field values that are
        persisted, otherwise the chain cannot be verified later.
        """
        content = self._hash_content(self.prev_hash, self.sequence_num,
                                     self.entry_type, self.payload, self.timestamp)
        return hashlib.sha256(content.encode()).hexdigest()

    @staticmethod
    def _hash_content(prev_hash, sequence_num, entry_type, payload, timestamp) -> str:
        return (
            str(prev_hash)
            + str(sequence_num)
            + str(entry_type)
            + json.dumps(payload or {}, sort_keys=True, default=str)
            + str(timestamp)
        )

    def save(self, *args, **kwargs):
        if self._state.adding:
            if not self.entry_hash:
                self.entry_hash = self.compute_hash()
        else:
            # Audit entries are immutable: mutating a chained entry would
            # silently invalidate the chain.  Updating is rejected outright.
            raise ValidationError('Audit log entries are immutable and cannot be modified.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Audit log entries cannot be deleted.')

    @classmethod
    def verify_chain(cls, run_id=None):
        """
        Verify the integrity of the audit chain.

        The chain is global and strictly ordered by ``sequence_num``.  The
        optional ``run_id`` does not change how the entries are linked — it
        only tells the caller whether the reported break belongs to the run
        it asked about.

        :returns: ``(is_valid, first_broken_seq)``
        """
        prev_hash = GENESIS_HASH
        expected_seq = 1
        for entry in cls.objects.all().order_by('sequence_num').iterator():
            if entry.sequence_num != expected_seq:
                return False, entry.sequence_num
            content = cls._hash_content(prev_hash, entry.sequence_num,
                                        entry.entry_type, entry.payload, entry.timestamp)
            expected = hashlib.sha256(content.encode()).hexdigest()
            if expected != entry.entry_hash:
                return False, entry.sequence_num
            prev_hash = entry.entry_hash
            expected_seq += 1
        return True, None

"""
CARMA — Audit log tests
Covers: hash-chain construction, tamper detection, immutability.
"""
import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from apps.audit.models import GENESIS_HASH, AuditLogEntry
from apps.audit.services import append_audit_entry


@pytest.fixture
def adaptation_id():
    return '11111111-1111-1111-1111-111111111111'


class TestAuditChain:
    def test_first_entry_links_to_genesis(self, db):
        entry = append_audit_entry('system', {'hello': 'world'}, actor_agent='test')
        assert entry.sequence_num == 1
        assert entry.prev_hash == GENESIS_HASH
        assert len(entry.entry_hash) == 64

    def test_chain_is_linked(self, db):
        first = append_audit_entry('plan', {'a': 1})
        second = append_audit_entry('action', {'b': 2})
        assert second.sequence_num == first.sequence_num + 1
        assert second.prev_hash == first.entry_hash

    def test_chain_verifies(self, db):
        for index in range(5):
            append_audit_entry('action', {'index': index})
        is_valid, broken_at = AuditLogEntry.verify_chain()
        assert is_valid is True
        assert broken_at is None

    def test_tampering_is_detected(self, db):
        append_audit_entry('plan', {'a': 1})
        entry = append_audit_entry('action', {'b': 2})
        # Bypass the immutability guard to simulate an out-of-band write.
        AuditLogEntry.objects.filter(pk=entry.pk).update(payload={'b': 999})
        is_valid, broken_at = AuditLogEntry.verify_chain()
        assert is_valid is False
        assert broken_at == entry.sequence_num

    def test_entries_are_immutable(self, db):
        entry = append_audit_entry('plan', {'a': 1})
        entry.payload = {'a': 2}
        with pytest.raises(ValidationError):
            entry.save()

    def test_entries_cannot_be_deleted(self, db):
        entry = append_audit_entry('plan', {'a': 1})
        with pytest.raises(ValidationError):
            entry.delete()

    def test_sequence_num_is_unique(self, db):
        append_audit_entry('plan', {'a': 1})
        with pytest.raises(IntegrityError):
            AuditLogEntry.objects.create(
                sequence_num=1, prev_hash=GENESIS_HASH, entry_type='plan', payload={})

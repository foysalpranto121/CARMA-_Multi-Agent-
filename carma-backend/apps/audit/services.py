"""
Audit log service — appends entries to the hash chain.

The chain is global and strictly ordered, so appending must be serialised.
``select_for_update`` on the last entry inside a transaction prevents two
Celery workers from claiming the same ``sequence_num``; the unique constraint
on ``sequence_num`` is the final safety net.
"""
from __future__ import annotations

import logging

from django.db import IntegrityError, connection, transaction

from apps.audit.models import GENESIS_HASH, AuditLogEntry

log = logging.getLogger('carma')

MAX_APPEND_RETRIES = 5


def append_audit_entry(entry_type: str, payload: dict,
                       run_id=None, adaptation_id=None, case_id: str = '',
                       actor_user=None, actor_agent: str = '') -> AuditLogEntry:
    """
    Append one entry to the hash-chained audit log.

    :param entry_type:    one of ``AuditLogEntry.ENTRY_TYPES``
    :param payload:      JSON-serialisable content of the entry
    :param run_id:       the experiment run the entry belongs to
    :param adaptation_id: the adaptation the entry belongs to
    :param case_id:      the benchmark case id
    :param actor_user:   the acting user (optional)
    :param actor_agent:  the acting agent name (optional)
    """
    last_error: Exception | None = None
    for _ in range(MAX_APPEND_RETRIES):
        try:
            with transaction.atomic():
                queryset = AuditLogEntry.objects
                if connection.features.has_select_for_update:
                    queryset = queryset.select_for_update()
                last = queryset.order_by('-sequence_num').first()
                sequence_num = (last.sequence_num + 1) if last else 1
                prev_hash = last.entry_hash if last else GENESIS_HASH
                return AuditLogEntry.objects.create(
                    sequence_num=sequence_num,
                    prev_hash=prev_hash,
                    entry_type=entry_type,
                    run_id=run_id,
                    adaptation_id=adaptation_id,
                    case_id=case_id or '',
                    payload=payload or {},
                    actor_user=actor_user,
                    actor_agent=actor_agent or '',
                )
        except IntegrityError as exc:
            # Another worker claimed the same sequence number — retry.
            last_error = exc
            log.debug('Audit append conflict, retrying: %s', exc)
    log.error('Could not append audit entry after %d attempts: %s',
              MAX_APPEND_RETRIES, last_error)
    raise last_error

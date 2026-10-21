"""
CARMA — Platform status views.

Reports the *real* state of the running stack (database, LLM provider,
vector store, task broker) so the frontend never has to display hardcoded
"ONLINE" indicators.  All probes are cached for a short period because they
touch the network.
"""
from __future__ import annotations

import socket
import time
from urllib.parse import urlparse

from django.conf import settings
from django.db import connection
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

PROBE_TIMEOUT_S = 1.5
CACHE_TTL_S     = 30.0

_probe_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, producer):
    now = time.monotonic()
    entry = _probe_cache.get(key)
    if entry and (now - entry[0]) < CACHE_TTL_S:
        return entry[1]
    value = producer()
    _probe_cache[key] = (now, value)
    return value


def _tcp_probe(url: str) -> bool:
    """TCP-connect to the host:port of ``url`` and report success."""
    if not url:
        return False
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port
    if not host:
        return False
    if port is None:
        port = 443 if parsed.scheme == 'https' else 80
    try:
        with socket.create_connection((host, port), timeout=PROBE_TIMEOUT_S):
            return True
    except OSError:
        return False


def _database_status() -> str:
    try:
        connection.ensure_connection()
        return 'ok'
    except Exception:
        return 'unreachable'


def _is_placeholder(value: str) -> bool:
    """
    A copied ``.env.example`` still contains template values.  Those must not be
    reported as "configured" — the dashboard would then claim a working LLM
    provider that does not exist.
    """
    if not value:
        return True
    lowered = value.strip().lower()
    markers = ('your-key', 'your_key', 'sk-your', 'changeme', 'change-me',
               'placeholder', 'xxxx', '<your')
    return any(marker in lowered for marker in markers)


def _llm_status() -> dict:
    """
    Report which LLM back-end is configured.

    A provider only counts as configured when a real credential is present —
    a copied ``.env.example`` must not be reported as a working LLM.
    """
    api_key = getattr(settings, 'OPENAI_API_KEY', '') or ''
    ollama_url = getattr(settings, 'OLLAMA_BASE_URL', '') or ''
    has_key = not _is_placeholder(api_key)

    if has_key:
        return {
            'configured': True,
            'provider': 'openai-compatible',
            'base_url': getattr(settings, 'OPENAI_BASE_URL', ''),
            'api_key_present': True,
            'reachable': None,
        }
    if ollama_url:
        return {
            'configured': True,
            'provider': 'ollama',
            'base_url': ollama_url,
            'api_key_present': False,
            'reachable': _cached('ollama', lambda: _tcp_probe(ollama_url)),
        }
    return {
        'configured': False,
        'provider': 'none',
        'base_url': '',
        'api_key_present': False,
        'reachable': False,
    }


def _vector_store_status() -> dict:
    url = getattr(settings, 'QDRANT_URL', '') or ''
    return {
        'configured': bool(url),
        'reachable': _cached('qdrant', lambda: _tcp_probe(url)) if url else False,
        'url': url,
    }


def _broker_status() -> dict:
    url = getattr(settings, 'CELERY_BROKER_URL', '') or ''
    return {
        'configured': bool(url),
        'reachable': _cached('broker', lambda: _tcp_probe(url)) if url else False,
    }


class SystemStatusView(APIView):
    """Live status of the platform components and the size of the dataset."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.benchmark.models import BenchmarkCase, BenchmarkScenario
        from apps.experiments.models import Adaptation, ExperimentRun, RunConfiguration
        from apps.processes.models import ConstraintSet, Process
        from apps.reviews.models import Escalation

        database = _cached('database', _database_status)

        counts = {}
        for label, model in (
            ('processes',        Process),
            ('constraint_sets',  ConstraintSet),
            ('scenarios',        BenchmarkScenario),
            ('benchmark_cases',  BenchmarkCase),
            ('configurations',   RunConfiguration),
            ('runs',             ExperimentRun),
            ('adaptations',      Adaptation),
        ):
            try:
                counts[label] = model.objects.count()
            except Exception:
                counts[label] = None

        try:
            counts['escalations_pending'] = Escalation.objects.filter(
                status__in=('pending', 'assigned')).count()
        except Exception:
            counts['escalations_pending'] = None

        from carma_engine.runners import RUNNER_MATRIX  # noqa: PLC0415

        overall = 'ok' if database == 'ok' else 'degraded'

        return Response({
            'status':    overall,
            'database':  database,
            'llm':       _llm_status(),
            'vector_store': _vector_store_status(),
            'task_broker':  _broker_status(),
            'engine': {
                'version': '1.0.0',
                'configurations': sorted(RUNNER_MATRIX),
            },
            'counts': counts,
            'timestamp': time.time(),
        })

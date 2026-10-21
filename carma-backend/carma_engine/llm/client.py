"""
Minimal, dependency-free LLM transport.

Two provider families are supported:

  * OpenAI-compatible chat completions (``gpt-4o``, ``gpt-4o-mini``, any
    local server exposing ``/v1/chat/completions``)
  * Ollama chat API (the open-weights models used in the factorial study:
    ``llama3.1-70b``, ``llama3.1-8b``, ``mistral-7b``, ``qwen2.5-32b``)

Design constraints that matter for the research protocol:

  * **Deterministic mode.**  When no endpoint/credential is configured the
    client raises :class:`LLMUnavailable` instead of silently returning
    fabricated text.  Callers must handle it explicitly (the runners fall
    back to the rule-based baseline B0), so an experiment can never record
    LLM output that was not actually produced by a model.
  * **Usage accounting.**  Prompt/completion token counts and the number of
    calls are tracked, because ``usd_cost`` and ``llm_call_count`` are
    reported metrics in the paper.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

log = logging.getLogger('carma')

DEFAULT_TIMEOUT = 120

# Approximate token estimate when the provider does not report usage.
_CHARS_PER_TOKEN = 4

OPENAI_MODELS = ('gpt-4o', 'gpt-4o-mini')
OLLAMA_MODELS = ('llama3.1-70b', 'llama3.1-8b', 'mistral-7b', 'qwen2.5-32b')


class LLMUnavailable(RuntimeError):
    """Raised when no usable LLM endpoint is configured."""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMClient:
    """
    Thin chat client.

    :param model:       model identifier (see :data:`OPENAI_MODELS` / :data:`OLLAMA_MODELS`)
    :param temperature: sampling temperature
    :param max_tokens:  completion cap
    :param seed:        optional seed forwarded to the provider
    """

    model: str = 'gpt-4o'
    temperature: float = 0.0
    max_tokens: int = 4096
    seed: int | None = None
    timeout: int = DEFAULT_TIMEOUT
    usage: Usage = field(default_factory=Usage)

    # ── configuration helpers ──────────────────────────────────
    def __post_init__(self):
        self._api_key = os.environ.get('OPENAI_API_KEY', '').strip()
        self._ollama_base = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
        self._openai_base = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/')

    @property
    def provider(self) -> str:
        return 'ollama' if self.model in OLLAMA_MODELS else 'openai'

    def available(self) -> bool:
        """True when the configured model can actually be reached."""
        if self.provider == 'ollama':
            return bool(self._ollama_base)
        return bool(self._api_key) and 'your-' not in self._api_key.lower()

    def _require(self):
        if not self.available():
            raise LLMUnavailable(
                f'No LLM endpoint available for model "{self.model}". '
                'Set OPENAI_API_KEY or OLLAMA_BASE_URL.'
            )

    # ── public API ────────────────────────────────────────────
    def invoke(self, system_prompt: str, human_prompt: str) -> str:
        """Single-turn chat completion. Returns the assistant text."""
        self._require()
        if self.provider == 'ollama':
            text, usage = self._call_ollama(system_prompt, human_prompt)
        else:
            text, usage = self._call_openai(system_prompt, human_prompt)

        self.usage.calls += 1
        self.usage.prompt_tokens += usage.get('prompt_tokens', self._estimate(system_prompt + human_prompt))
        self.usage.completion_tokens += usage.get('completion_tokens', self._estimate(text))
        return text

    def invoke_json(self, system_prompt: str, human_prompt: str, default: dict | None = None) -> dict:
        """
        Chat completion parsed as a JSON object.

        Model output is frequently wrapped in a markdown fence or followed by
        prose; the parser strips both before decoding.  When decoding still
        fails the caller-supplied ``default`` is returned so the pipeline
        degrades instead of crashing mid-experiment.
        """
        raw = self.invoke(system_prompt, human_prompt)
        return parse_json_object(raw, default if default is not None else {})

    # ── providers ─────────────────────────────────────────────
    def _call_openai(self, system_prompt: str, human_prompt: str) -> tuple[str, dict]:
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': human_prompt},
            ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
        }
        if self.seed is not None:
            payload['seed'] = self.seed
        request = urllib.request.Request(
            f'{self._openai_base}/chat/completions',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self._api_key}',
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            raise LLMUnavailable(f'OpenAI request failed: {exc}') from exc
        except urllib.error.URLError as exc:
            raise LLMUnavailable(f'OpenAI endpoint unreachable: {exc}') from exc

        try:
            message = body['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailable('Malformed OpenAI response.') from exc
        return message or '', body.get('usage') or {}

    def _call_ollama(self, system_prompt: str, human_prompt: str) -> tuple[str, dict]:
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': human_prompt},
            ],
            'stream': False,
            'options': {
                'temperature': self.temperature,
                'num_predict': self.max_tokens,
                **({'seed': self.seed} if self.seed is not None else {}),
            },
        }
        request = urllib.request.Request(
            f'{self._ollama_base}/api/chat',
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            raise LLMUnavailable(f'Ollama request failed: {exc}') from exc
        except urllib.error.URLError as exc:
            raise LLMUnavailable(f'Ollama endpoint unreachable: {exc}') from exc

        message = (body.get('message') or {}).get('content', '')
        usage = {
            'prompt_tokens': body.get('prompt_eval_count', 0),
            'completion_tokens': body.get('eval_count', 0),
        }
        return message, usage

    @staticmethod
    def _estimate(text: str) -> int:
        return max(1, len(text or '') // _CHARS_PER_TOKEN)


_FENCE_RE = re.compile(r'```(?:json)?\s*(.*?)\s*```', re.DOTALL)


def parse_json_object(raw: str, default: dict) -> dict:
    """Best-effort extraction of a JSON object from raw model output."""
    if not raw:
        return default
    candidates = [raw]
    fenced = _FENCE_RE.search(raw)
    if fenced:
        candidates.append(fenced.group(1))
    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end > start:
        candidates.append(raw[start:end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    log.warning('Could not decode JSON from model output; using default.')
    return default


def build_llm(model: str = 'gpt-4o', temperature: float = 0.0,
               max_tokens: int = 4096, seed: int | None = None) -> LLMClient:
    """Factory used by the runners."""
    return LLMClient(model=model, temperature=temperature, max_tokens=max_tokens, seed=seed)

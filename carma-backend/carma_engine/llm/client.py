"""
Minimal LLM transport.

Three provider families are supported:

  * Anthropic Claude Messages API (``claude-opus-5-5``, ``claude-sonnet-5-5``,
    ``claude-haiku-5-5``) through the official ``anthropic`` SDK
  * OpenAI-compatible chat completions (``gpt-4o``, ``gpt-4o-mini``, any
    local server exposing ``/v1/chat/completions``)
  * Ollama chat API (the open-weights models used in the factorial study:
    ``llama3.1-70b``, ``llama3.1-8b``, ``mistral-7b``, ``qwen2.5-32b``)

Credentials and endpoints are read from the process environment first and
from ``carma-backend/.env`` second (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``,
``OLLAMA_BASE_URL`` ...) — the same precedence the Django settings use.

Design constraints that matter for the research protocol:

  * **No silent substitution.**  When no endpoint/credential is configured
    the client raises :class:`LLMUnavailable` instead of returning
    fabricated text, and the agents let it propagate, so the case is
    recorded as failed.  An experiment can never record LLM output that was
    not actually produced by a model.
  * **Sampling parameters.**  The Claude API accepts no ``temperature``,
    ``top_p``, ``top_k`` or ``seed`` (API version 2026-10-21), so for Claude
    models the configured temperature and seed are not sent: repeated seeds
    are repeated samples at the provider default.
  * **Usage accounting.**  Prompt/completion token counts, the number of
    calls, the model that actually served each call and the list-price cost
    are tracked, because ``usd_cost`` and ``llm_call_count`` are reported
    metrics in the paper.
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

DEFAULT_MODEL = 'claude-opus-5-5'

CLAUDE_MODELS = ('claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5')
OPENAI_MODELS = ('gpt-4o', 'gpt-4o-mini')
OLLAMA_MODELS = ('llama3.1-70b', 'llama3.1-8b', 'mistral-7b', 'qwen2.5-32b')

# The configuration stores dash-separated model ids; Ollama names its
# models ``family:size``.
OLLAMA_TAGS = {
    'llama3.1-70b': 'llama3.1:70b',
    'llama3.1-8b':  'llama3.1:8b',
    'mistral-7b':   'mistral:7b',
    'qwen2.5-32b':  'qwen2.5:32b',
}

# Claude list prices in USD per million (input, output) tokens on the run
# date.  The server-side fallback targets are listed too, because a
# declined request is served — and billed — by one of them.
CLAUDE_PRICES = {
    'claude-opus-5-5':   (4.00, 20.00),
    'claude-sonnet-5-5': (2.00, 10.00),
    'claude-haiku-5-5':  (0.10, 0.50),
    'claude-opus-5':     (5.00, 25.00),
    'claude-opus-4-8':   (5.00, 25.00),
    'claude-sonnet-5':   (2.00, 10.00),
}

# Thinking is always on for the current Claude models and is billed against
# ``max_tokens``, so a smaller cap would truncate the answer.
CLAUDE_MIN_MAX_TOKENS = 16000

# Claude Haiku 5.5 has no server-side refusal fallback.
_NO_FALLBACK_MODELS = ('claude-haiku-5-5',)


def _env(name: str, default: str = '') -> str:
    """A setting from the process environment, else from ``carma-backend/.env``."""
    try:
        from decouple import config  # noqa: PLC0415
    except ImportError:  # pragma: no cover - python-decouple is a core requirement
        return os.environ.get(name, default)
    return str(config(name, default=default))


def _is_placeholder(key: str) -> bool:
    return not key or 'your-' in key.lower() or key.endswith('...')


def claude_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """List-price cost of one Claude call, or ``None`` for an unpriced model."""
    prices = CLAUDE_PRICES.get(model)
    if prices is None:
        return None
    return (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000


class LLMUnavailable(RuntimeError):
    """Raised when no usable LLM endpoint is configured."""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    usd_cost: float = 0.0
    refusals: int = 0
    fallbacks: int = 0
    # model id -> number of calls it served (differs from the configured
    # model when a refused request fell back to another model)
    served_by: dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMClient:
    """
    Thin chat client.

    :param model:       model identifier (see :data:`CLAUDE_MODELS`,
                        :data:`OPENAI_MODELS` and :data:`OLLAMA_MODELS`)
    :param temperature: sampling temperature (not sent to Claude)
    :param max_tokens:  completion cap
    :param seed:        optional seed forwarded to the provider (not sent to Claude)
    :param effort:      Claude ``output_config.effort``; defaults to
                        ``ANTHROPIC_EFFORT`` or ``medium``
    """

    model: str = DEFAULT_MODEL
    temperature: float = 0.0
    max_tokens: int = 4096
    seed: int | None = None
    timeout: int = DEFAULT_TIMEOUT
    effort: str = ''
    usage: Usage = field(default_factory=Usage)

    # ── configuration helpers ──────────────────────────────────
    def __post_init__(self):
        self._api_key = _env('OPENAI_API_KEY').strip()
        self._anthropic_key = _env('ANTHROPIC_API_KEY').strip()
        self._ollama_base = _env('OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
        self._openai_base = _env('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
        self.effort = self.effort or _env('ANTHROPIC_EFFORT', 'medium')
        self._anthropic = None

    @property
    def provider(self) -> str:
        if self.model.startswith('claude-'):
            return 'anthropic'
        return 'ollama' if self.model in OLLAMA_MODELS else 'openai'

    def available(self) -> bool:
        """True when the configured model can actually be reached."""
        if self.provider == 'anthropic':
            return not _is_placeholder(self._anthropic_key)
        if self.provider == 'ollama':
            return bool(self._ollama_base)
        return not _is_placeholder(self._api_key)

    def _require(self):
        if not self.available():
            setting = {'anthropic': 'ANTHROPIC_API_KEY',
                       'ollama': 'OLLAMA_BASE_URL'}.get(self.provider, 'OPENAI_API_KEY')
            raise LLMUnavailable(
                f'No LLM endpoint available for model "{self.model}". '
                f'Set {setting} in carma-backend/.env.'
            )

    # ── public API ────────────────────────────────────────────
    def invoke(self, system_prompt: str, human_prompt: str) -> str:
        """Single-turn chat completion. Returns the assistant text."""
        self._require()
        if self.provider == 'anthropic':
            text, usage = self._call_anthropic(system_prompt, human_prompt)
        elif self.provider == 'ollama':
            text, usage = self._call_ollama(system_prompt, human_prompt)
        else:
            text, usage = self._call_openai(system_prompt, human_prompt)

        self.usage.calls += 1
        self.usage.prompt_tokens += usage.get('prompt_tokens', self._estimate(system_prompt + human_prompt))
        self.usage.completion_tokens += usage.get('completion_tokens', self._estimate(text))
        self.usage.usd_cost += usage.get('usd_cost') or 0.0
        self.usage.refusals += int(bool(usage.get('refusal')))
        self.usage.fallbacks += int(bool(usage.get('fallback')))
        served = usage.get('model') or self.model
        self.usage.served_by[served] = self.usage.served_by.get(served, 0) + 1
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
    def _call_anthropic(self, system_prompt: str, human_prompt: str) -> tuple[str, dict]:
        import anthropic  # noqa: PLC0415

        if self._anthropic is None:
            self._anthropic = anthropic.Anthropic(api_key=self._anthropic_key, max_retries=5)
        params = {
            'model': self.model,
            'max_tokens': max(self.max_tokens, CLAUDE_MIN_MAX_TOKENS),
            'system': system_prompt,
            'messages': [{'role': 'user', 'content': human_prompt}],
            'output_config': {'effort': self.effort},
        }
        if self.model not in _NO_FALLBACK_MODELS:
            # A request the safety classifiers decline is re-run server-side
            # on the model Anthropic recommends for the refusal category; the
            # model that served the call is recorded in the usage.
            params['betas'] = ['server-side-fallback-2026-07-01']
            params['fallbacks'] = 'default'
        try:
            response = self._anthropic.beta.messages.create(**params)
        except anthropic.AuthenticationError as exc:
            raise LLMUnavailable('Claude rejected ANTHROPIC_API_KEY.') from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMUnavailable(f'The API key may not use "{self.model}".') from exc
        except anthropic.NotFoundError as exc:
            raise LLMUnavailable(f'Unknown Claude model "{self.model}".') from exc
        except anthropic.RateLimitError as exc:
            raise LLMUnavailable('Claude rate limit still exceeded after retries.') from exc
        except anthropic.APIStatusError as exc:
            raise LLMUnavailable(f'Claude request failed ({exc.status_code}): {exc.message}') from exc
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailable(f'Claude API unreachable: {exc}') from exc

        refused = response.stop_reason == 'refusal'
        if refused:
            category = getattr(response.stop_details, 'category', None)
            log.warning('Claude declined the request (category=%s).', category)
            text = ''
        else:
            text = ''.join(block.text for block in response.content if block.type == 'text')
            if response.stop_reason == 'max_tokens':
                log.warning('Claude response truncated at max_tokens=%s.', params['max_tokens'])

        fallback = any(getattr(entry, 'type', '') == 'fallback_message'
                       for entry in (response.usage.iterations or []))
        input_tokens = response.usage.input_tokens or 0
        output_tokens = response.usage.output_tokens or 0
        cost = claude_cost(response.model, input_tokens, output_tokens)
        if cost is None:
            log.warning('No list price recorded for "%s"; usd_cost is under-reported.', response.model)
        return text, {
            'prompt_tokens': input_tokens,
            'completion_tokens': output_tokens,
            'model': response.model,
            'usd_cost': cost,
            'refusal': refused,
            'fallback': fallback,
        }

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
        usage = dict(body.get('usage') or {})
        # The dated snapshot that answered (e.g. gpt-4o-2024-08-06): the
        # protocol pins model versions, so the served one is recorded.
        usage['model'] = body.get('model') or self.model
        return message or '', usage

    def _call_ollama(self, system_prompt: str, human_prompt: str) -> tuple[str, dict]:
        payload = {
            'model': OLLAMA_TAGS.get(self.model, self.model),
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


def build_llm(model: str = DEFAULT_MODEL, temperature: float = 0.0,
               max_tokens: int = 4096, seed: int | None = None) -> LLMClient:
    """Factory used by the runners."""
    return LLMClient(model=model, temperature=temperature, max_tokens=max_tokens, seed=seed)

"""Provider adapters behind a model allowlist. Importing this module makes no network call and
needs no key; a client is created only when a paid command actually dispatches a request."""

import json
import os
import time
from dataclasses import dataclass

from .labels import BATCH_SCHEMA


@dataclass(frozen=True)
class ModelSpec:
    name: str            # allowlist key used on the command line
    provider: str        # "openai" | "anthropic"
    model: str           # exact API model ID, logged on every call
    effort: str          # reasoning effort sent, or "default" when the model takes none
    out_per_review: int  # output-token cap per review in the batch
    out_overhead: int    # extra output allowance per request (JSON wrapper, reasoning)
    role: str            # "primary" or "fallback"

    def max_output_tokens(self, n_reviews):
        return self.out_overhead + self.out_per_review * n_reviews


# Only these configurations may be dispatched. Anything else is refused before any request.
ALLOWLIST = {
    s.name: s
    for s in (
        ModelSpec("luna-none", "openai", "gpt-6-luna", "none", 120, 300, "primary"),
        ModelSpec("luna-low", "openai", "gpt-6-luna", "low", 120, 3000, "primary"),
        ModelSpec("haiku", "anthropic", "claude-haiku-4-5", "default", 120, 300, "primary"),
        ModelSpec("sonnet-low", "anthropic", "claude-sonnet-5-5", "low", 120, 3000, "fallback"),
    )
}

KEY_ENV = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def get_spec(name):
    if name not in ALLOWLIST:
        raise ValueError(f"model config {name!r} is not on the allowlist: {sorted(ALLOWLIST)}")
    return ALLOWLIST[name]


@dataclass
class CallResult:
    ok: bool                 # transport succeeded and a response body came back
    retryable: bool          # for failures: worth another attempt after backoff
    parsed: dict | None      # JSON body when it parsed
    usage: dict              # input / cached_input / cache_write / output / reasoning (info only)
    request_id: str | None
    latency_s: float
    finish: str | None       # provider status / stop reason
    error: str | None = None


def _missing_key(provider):
    env = KEY_ENV[provider]
    if not os.environ.get(env):
        raise RuntimeError(f"{env} is not set. Put it in .env (git-ignored); see .env.example.")


_clients = {}


def _client(provider):
    if provider not in _clients:
        _missing_key(provider)
        if provider == "openai":
            import openai
            _clients[provider] = openai.OpenAI(max_retries=0, timeout=120)  # we own retries and log each one
        else:
            import anthropic
            _clients[provider] = anthropic.Anthropic(max_retries=0, timeout=120)
    return _clients[provider]


def _parse(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _call_openai(spec, system, user, max_out, schema=BATCH_SCHEMA, name="review_labels"):
    import openai

    t0 = time.perf_counter()
    try:
        resp = _client("openai").responses.create(
            model=spec.model,
            instructions=system,
            input=user,
            reasoning={"effort": spec.effort},
            max_output_tokens=max_out,
            store=False,
            text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
        )
    except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError) as e:
        return CallResult(False, True, None, {}, None, time.perf_counter() - t0, None, f"{type(e).__name__}: {e}")
    except openai.APIStatusError as e:
        return CallResult(False, e.status_code >= 500, None, {}, getattr(e, "request_id", None),
                          time.perf_counter() - t0, None, f"{type(e).__name__} {e.status_code}: {e.message}")
    u = resp.usage
    cached = (u.input_tokens_details.cached_tokens or 0) if u.input_tokens_details else 0
    reasoning = (u.output_tokens_details.reasoning_tokens or 0) if u.output_tokens_details else 0
    usage = {"input": u.input_tokens - cached, "cached_input": cached, "cache_write": 0,
             "output": u.output_tokens, "reasoning": reasoning}
    return CallResult(True, False, _parse(resp.output_text), usage, resp.id, time.perf_counter() - t0, resp.status)


def _call_anthropic(spec, system, user, max_out, schema=BATCH_SCHEMA, name=None):
    import anthropic

    t0 = time.perf_counter()
    kwargs = dict(
        model=spec.model,
        max_tokens=max_out,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    if spec.effort != "default":
        kwargs["output_config"]["effort"] = spec.effort
    try:
        msg = _client("anthropic").messages.create(**kwargs)
    except (anthropic.RateLimitError, anthropic.APITimeoutError, anthropic.APIConnectionError,
            anthropic.InternalServerError, anthropic.OverloadedError) as e:
        return CallResult(False, True, None, {}, None, time.perf_counter() - t0, None, f"{type(e).__name__}: {e}")
    except anthropic.APIStatusError as e:
        return CallResult(False, e.status_code >= 500, None, {}, getattr(e, "request_id", None),
                          time.perf_counter() - t0, None, f"{type(e).__name__} {e.status_code}: {e.message}")
    u = msg.usage
    usage = {"input": u.input_tokens, "cached_input": u.cache_read_input_tokens or 0,
             "cache_write": u.cache_creation_input_tokens or 0, "output": u.output_tokens, "reasoning": None}
    text = next((b.text for b in msg.content if b.type == "text"), None)
    return CallResult(True, False, _parse(text), usage, msg._request_id or msg.id, time.perf_counter() - t0, msg.stop_reason)


def call(spec, system, user, max_out, schema=BATCH_SCHEMA, name="review_labels"):
    if spec.provider == "openai":
        return _call_openai(spec, system, user, max_out, schema, name)
    if spec.provider == "anthropic":
        return _call_anthropic(spec, system, user, max_out, schema, name)
    raise ValueError(spec.provider)

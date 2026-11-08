"""Provider adapter. The pipeline depends only on the LLMClient protocol.

- AnthropicClient: live calls. Forces structured output through a single tool
  whose input_schema is the stage schema. Optional dependency. Supports prompt
  caching (system prompt + index payload pinned as ephemeral cache breakpoints)
  and returns token-usage + request-ID metadata via ``last_usage``.
- ReplayClient: returns recorded stage outputs from a directory. Used by CI and
  tests so no live API is ever called there.
- RecordClient: wraps AnthropicClient and writes each response to a replay
  directory as it is received. One live run produces a fully reusable fixture
  (``--llm record --record-dir <dir>``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from .errors import Stop


class TransientLLMError(Exception):
    """Provider hiccup worth one retry: timeout, connection drop, rate limit, 5xx/overload."""


class BadOutputError(Exception):
    """The model answered, but not in a usable shape (e.g. no tool_use block)."""


# Returned by AnthropicClient.complete_json (and RecordClient) alongside the
# result dict so callers can persist it in run_metadata.json.
UsageInfo = dict  # keys: input_tokens, output_tokens, cache_read_tokens,
#                          cache_creation_tokens, request_id


class LLMClient(Protocol):
    name: str
    model: str
    temperature: float | None

    def complete_json(self, *, stage: str, system: str, user: str, schema: dict) -> dict: ...


def _tool_schema(schema: dict) -> dict:
    return {k: v for k, v in schema.items() if k not in ("$schema", "$id", "title")}


def _build_cached_system(system: str) -> list[dict]:
    """Wrap the system prompt as a cache-breakpoint block.

    ``cache_control`` tells Anthropic to store the prefix up to this block.
    ``common.md`` + the stage prompt never change between stages in a single run,
    so successive stage calls will read from cache instead of re-encoding.
    """
    return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]


def _build_cached_messages(user: str) -> list[dict]:
    """Wrap the (large) user payload as a cache-breakpoint block.

    The payload is the canonical index serialised as compact JSON.  It is
    identical across all retry attempts within a stage, so the second attempt
    benefits from the cache even without an explicit retry hint.
    """
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user, "cache_control": {"type": "ephemeral"}}
            ],
        }
    ]


class AnthropicClient:
    name = "anthropic"

    def __init__(
        self,
        model: str,
        temperature: float | None = 0.0,
        max_tokens: int = 16000,
        api_key: str | None = None,
    ) -> None:
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - exercised only without the extra
            raise Stop(
                "STOP: Missing dependency — anthropic — pip install 'design-agent[anthropic]'"
            ) from e
        self._anthropic = anthropic
        client_kwargs = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        self._client = anthropic.Anthropic(**client_kwargs)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        # Populated after every successful complete_json call; callers may read it.
        self.last_usage: UsageInfo = {}

    def complete_json(self, *, stage: str, system: str, user: str, schema: dict) -> dict:
        kwargs: dict[str, Any] = {}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        anthropic = self._anthropic
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_build_cached_system(system),
                messages=_build_cached_messages(user),
                tools=[
                    {
                        "name": "emit_artifact",
                        "description": f"Return the {stage} artifact.",
                        "input_schema": _tool_schema(schema),
                    }
                ],
                tool_choice={"type": "tool", "name": "emit_artifact"},
                **kwargs,
            )
        except (
            anthropic.APIConnectionError,  # includes APITimeoutError
            anthropic.RateLimitError,
            anthropic.InternalServerError,  # 5xx, incl. 529 overloaded
        ) as e:
            raise TransientLLMError(f"{type(e).__name__}: {e}") from e
        # Anything else (auth, permission, bad request, not found) propagates:
        # retrying cannot help.

        # Guard: if the model ran out of tokens the tool call may be truncated.
        # Treat this as a hard error — a partial JSON object silently written to
        # disk is worse than a loud STOP.
        if resp.stop_reason == "max_tokens":
            raise BadOutputError(
                f"model hit max_tokens ({self.max_tokens}) before finishing the tool call "
                f"for stage '{stage}'; increase max_tokens or reduce the payload"
            )

        # Record token usage and request ID for run_metadata.json.
        usage = resp.usage
        self.last_usage = {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None),
            "request_id": resp.id,
        }

        for block in resp.content:
            if block.type == "tool_use":
                return dict(block.input)
        raise BadOutputError(f"model returned no tool_use block (stop_reason={resp.stop_reason})")


class ReplayClient:
    name = "replay"
    model = "replay"
    temperature = None

    def __init__(self, replay_dir: Path) -> None:
        self.dir = Path(replay_dir)

    def complete_json(self, *, stage: str, system: str, user: str, schema: dict) -> dict:
        path = self.dir / f"{stage}.json"
        if not path.is_file():
            raise Stop(f"STOP: Replay — no recorded response for stage '{stage}' in {self.dir}")
        return json.loads(path.read_text(encoding="utf-8"))


class RecordClient:
    """Wraps AnthropicClient and saves each response as ``<record_dir>/<stage>.json``.

    After a successful run the record directory is a valid replay directory:
    pass it to ``ReplayClient`` (or ``--llm replay --replay-dir <dir>``) to
    re-run the pipeline without any further API calls.  This closes the gap
    "live adapter untested in CI" — one real run produces the fixture.

    Usage (CLI)::

        design-agent run input/ --out out/ --llm record --record-dir fixtures/my-run/

    The ``record_dir`` is created on first use.  Existing files are
    *overwritten* so a failed-then-retried run always leaves a consistent set.
    """

    name = "record"

    def __init__(self, inner: AnthropicClient, record_dir: Path) -> None:
        self._inner = inner
        self.record_dir = Path(record_dir)
        self.record_dir.mkdir(parents=True, exist_ok=True)

    # Delegate model / temperature to the wrapped client so run_metadata stays accurate.
    @property
    def model(self) -> str:
        return self._inner.model

    @property
    def temperature(self) -> float | None:
        return self._inner.temperature

    @property
    def last_usage(self) -> UsageInfo:
        return self._inner.last_usage

    def complete_json(self, *, stage: str, system: str, user: str, schema: dict) -> dict:
        result = self._inner.complete_json(stage=stage, system=system, user=user, schema=schema)
        path = self.record_dir / f"{stage}.json"
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return result

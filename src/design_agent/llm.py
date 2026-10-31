"""Provider adapter. The pipeline depends only on the LLMClient protocol.

- AnthropicClient: live calls. Forces structured output through a single tool
  whose input_schema is the stage schema. Optional dependency.
- ReplayClient: returns recorded stage outputs from a directory. Used by CI and
  tests so no live API is ever called there.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from .errors import Stop


class LLMClient(Protocol):
    name: str
    model: str
    temperature: float | None

    def complete_json(self, *, stage: str, system: str, user: str, schema: dict) -> dict: ...


def _tool_schema(schema: dict) -> dict:
    return {k: v for k, v in schema.items() if k not in ("$schema", "$id", "title")}


class AnthropicClient:
    name = "anthropic"

    def __init__(
        self, model: str, temperature: float | None = 0.0, max_tokens: int = 16000
    ) -> None:
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - exercised only without the extra
            raise Stop(
                "STOP: Missing dependency — anthropic — pip install 'design-agent[anthropic]'"
            ) from e
        self._client = anthropic.Anthropic()
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def complete_json(self, *, stage: str, system: str, user: str, schema: dict) -> dict:
        kwargs: dict[str, Any] = {}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
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
        for block in resp.content:
            if block.type == "tool_use":
                return dict(block.input)
        raise ValueError("model returned no tool_use block")


class ReplayClient:
    name = "replay"
    model = "replay"
    temperature = None

    def __init__(self, replay_dir: Path) -> None:
        self.dir = Path(replay_dir)

    def complete_json(self, *, stage: str, system: str, user: str, schema: dict) -> dict:
        path = self.dir / f"{stage}.json"
        if not path.is_file():
            raise ValueError(f"no recorded response for stage '{stage}' in {self.dir}")
        return json.loads(path.read_text(encoding="utf-8"))

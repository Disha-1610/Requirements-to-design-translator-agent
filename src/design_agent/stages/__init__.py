"""Stages 2-7. LLM stages (2-5) synthesize; code stages (6-7) derive mechanically.

Stage 6 (data model) and Stage 7 (validation checklist) are code, not LLM:
both are direct transformations of data already fixed by earlier artifacts, so
an LLM could only add risk (invention) and cost.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources

from jsonschema import Draft202012Validator

from ..errors import Stop
from ..llm import BadOutputError, LLMClient, TransientLLMError
from ..schemas import load_schema


@dataclass
class StageRecord:
    stage: str
    file: str
    prompt_sha256: str | None
    attempts: int


def load_prompt(name: str) -> str:
    base = resources.files("design_agent") / "prompts"
    return (base / "common.md").read_text(encoding="utf-8") + "\n\n" + (
        base / f"{name}.md"
    ).read_text(encoding="utf-8")


def compact(obj: object) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


Check = Callable[[dict], list[str]]

# Caps keep the repair prompt bounded; the model needs examples, not an exhaustive dump.
_MAX_PROBLEMS = 20
_MAX_REJECTED_CHARS = 60_000


def _repair_prompt(user: str, rejected: dict | None, problems: list[str]) -> str:
    listed = "\n".join(f"- {p}" for p in problems[:_MAX_PROBLEMS])
    if len(problems) > _MAX_PROBLEMS:
        listed += f"\n- ... and {len(problems) - _MAX_PROBLEMS} more of the same kind"
    parts = [user, "", "PREVIOUS OUTPUT REJECTED."]
    if rejected is not None:
        body = compact(rejected)
        if len(body) > _MAX_REJECTED_CHARS:
            body = body[:_MAX_REJECTED_CHARS] + " ...[truncated]"
        parts += ["Your previous output was:", body]
    parts += [
        "It failed these checks:",
        listed,
        "Return a corrected, complete artifact. Fix every listed problem. Use only IDs, "
        "fields, error codes and module names present in the input above; never invent one.",
    ]
    return "\n".join(parts)


def run_llm_stage(
    client: LLMClient,
    *,
    number: int,
    name: str,
    file: str,
    payload: dict,
    check: Check | None = None,
) -> tuple[dict, StageRecord]:
    """Call the LLM, validate, one repair retry, then STOP.

    An output is rejected if it fails the stage schema or, once schema-valid, if
    `check` (the Stage 8 checks that apply to this stage) reports problems. The
    repair prompt carries the rejected output and every problem found.

    Only transient provider errors and bad output are retried. Anything else
    (authentication, bad request, a bug in our code) propagates immediately.
    """
    schema = load_schema(name)
    system = load_prompt(name)
    user = compact(payload)
    validator = Draft202012Validator(schema)
    rejected: dict | None = None
    problems: list[str] = []
    transient: str | None = None
    for attempt in (1, 2):
        prompt = user if not problems else _repair_prompt(user, rejected, problems)
        try:
            result = client.complete_json(stage=name, system=system, user=prompt, schema=schema)
        except TransientLLMError as e:
            # Nothing was produced: retry the same request, keeping any earlier repair context.
            transient = f"{type(e).__name__}: {e}"
            continue
        except BadOutputError as e:
            transient, rejected, problems = None, None, [str(e)]
            continue
        transient = None
        if not isinstance(result, dict):
            rejected, problems = None, [f"-: expected a JSON object, got {type(result).__name__}"]
            continue
        problems = [
            f"{'/'.join(str(p) for p in err.absolute_path) or '-'}: {err.message[:120]}"
            for err in validator.iter_errors(result)
        ]
        if not problems and check is not None:
            problems = check(result)
        if not problems:
            digest = hashlib.sha256(system.encode()).hexdigest()
            return result, StageRecord(name, file, digest, attempt)
        rejected = result
    reason = transient if transient else "; ".join(problems[:3])
    if not transient and len(problems) > 3:
        reason += f" (+{len(problems) - 3} more)"
    raise Stop(
        f"STOP: Stage {number} — {name} — {file} — LLM output invalid after 1 repair — {reason}",
        stage=str(number),
    )

"""Stages 2-7. LLM stages (2-5) synthesize; code stages (6-7) derive mechanically.

Stage 6 (data model) and Stage 7 (validation checklist) are code, not LLM:
both are direct transformations of data already fixed by earlier artifacts, so
an LLM could only add risk (invention) and cost.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources

from jsonschema import Draft202012Validator

from ..errors import Stop
from ..llm import LLMClient
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


def run_llm_stage(
    client: LLMClient, *, number: int, name: str, file: str, payload: dict
) -> tuple[dict, StageRecord]:
    """Call the LLM, validate against the stage schema, one repair retry, then STOP."""
    schema = load_schema(name)
    system = load_prompt(name)
    user = compact(payload)
    validator = Draft202012Validator(schema)
    last_problem = ""
    for attempt in (1, 2):
        prompt = user if attempt == 1 else f"{user}\n\nPREVIOUS OUTPUT REJECTED: {last_problem}"
        try:
            result = client.complete_json(stage=name, system=system, user=prompt, schema=schema)
        except Exception as e:  # provider/network/parse failure
            last_problem = f"{type(e).__name__}: {e}"
            continue
        problems = [
            f"{'/'.join(str(p) for p in err.absolute_path) or '-'}: {err.message[:120]}"
            for err in validator.iter_errors(result)
        ]
        if not problems:
            digest = hashlib.sha256(system.encode()).hexdigest()
            return result, StageRecord(name, file, digest, attempt)
        last_problem = "; ".join(problems[:3])
    raise Stop(
        f"STOP: Stage {number} — {name} — {file} — LLM output invalid after 1 repair — {last_problem}",
        stage=str(number),
    )

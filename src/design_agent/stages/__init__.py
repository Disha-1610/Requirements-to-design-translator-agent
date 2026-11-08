"""Stages 2-7. LLM stages (2-5) synthesize; code stages (6-7) derive mechanically.

Stage 6 (data model) and Stage 7 (validation checklist) are code, not LLM:
both are direct transformations of data already fixed by earlier artifacts, so
an LLM could only add risk (invention) and cost.

Scaling (module sharding)
--------------------------
Each LLM stage builds one payload covering the whole requirement set.  For
large FRDs this can hit model context or output limits.  ``run_sharded_stage``
splits the work by module after Stage 2:

  1. Partition requirements by which module's screens / APIs / entities are
     relevant (derived from the golden-thread links in ``index.links``).
  2. Call ``run_llm_stage`` once per shard; collect the per-module results.
  3. Merge the ``{top_key: [...]}`` lists from all shards into a single dict.
  4. Run the cross-shard ``check`` on the merged result, so constraints that
     span module boundaries (Golden Thread, schema) are still enforced.

Callers opt in by passing ``shard_by`` (a function that maps the arch dict to
a list of ``{module, item_key, items}`` dicts) and ``merge_key`` (the top-level
JSON array key).  Stages that have a single small payload continue to call
``run_llm_stage`` directly with no changes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

from ..errors import Stop
from ..llm import BadOutputError, LLMClient, TransientLLMError, UsageInfo
from ..schemas import load_schema

# Token budget above which a stage switches to sharded mode automatically.
# Rough heuristic: compact JSON is ~4 chars/token; 60 000 chars ≈ 15 000 tokens,
# comfortably below the 32 k-token output limit while leaving room for the
# system prompt and schema.
SHARD_THRESHOLD_CHARS = 60_000


@dataclass
class StageRecord:
    stage: str
    file: str
    prompt_sha256: str | None
    attempts: int
    usage: UsageInfo = field(default_factory=dict)


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


def _get_usage(client: Any) -> UsageInfo:
    """Pull last_usage off the client if it exposes one (AnthropicClient / RecordClient)."""
    return dict(getattr(client, "last_usage", {}))


def _merge_usages(usages: list[UsageInfo]) -> UsageInfo:
    """Sum numeric fields across multiple shard usages; last request_id wins."""
    merged: UsageInfo = {}
    for u in usages:
        for k, v in u.items():
            if k == "request_id":
                merged[k] = v
            elif isinstance(v, (int, float)) and v is not None:
                merged[k] = merged.get(k, 0) + v
    return merged


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

    Reproducibility: the prompt hash covers both the system prompt and the
    serialised payload so that any change to either produces a different digest,
    making a run fully identifiable from its metadata alone.
    """
    schema = load_schema(name)
    system = load_prompt(name)
    # Serialise once; reuse the string for hashing *and* for the API call.
    # This closes the small window where a file could change between hash and read.
    user = compact(payload)
    # Hash system + payload together for a fully-identifying run fingerprint.
    combined_digest = hashlib.sha256((system + user).encode()).hexdigest()
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
            return result, StageRecord(
                name, file, combined_digest, attempt, usage=_get_usage(client)
            )
        rejected = result
    reason = transient if transient else "; ".join(problems[:3])
    if not transient and len(problems) > 3:
        reason += f" (+{len(problems) - 3} more)"
    raise Stop(
        f"STOP: Stage {number} — {name} — {file} — LLM output invalid after 1 repair — {reason}",
        stage=str(number),
    )


# ---------------------------------------------------------------------------
# Module-sharded stage runner
# ---------------------------------------------------------------------------

ShardSpec = list[dict]  # Each dict: {"module": str, "shard_payload": dict}


def build_module_shards(
    base_payload: dict,
    arch: dict,
    module_payload_fn: Callable[[str, dict, dict], dict],
) -> ShardSpec:
    """Return one shard dict per architecture module.

    ``module_payload_fn(module_name, module_def, base_payload)`` must return
    the stage-specific slice of the payload for that module.  ``base_payload``
    carries fields that are the same for every shard (e.g. ``requirements``,
    ``errors``).
    """
    return [
        {
            "module": m["name"],
            "shard_payload": module_payload_fn(m["name"], m, base_payload),
        }
        for m in arch["modules"]
    ]


def run_sharded_stage(
    client: LLMClient,
    *,
    number: int,
    name: str,
    file: str,
    full_payload: dict,
    merge_key: str,
    shards: ShardSpec,
    check: Check | None = None,
) -> tuple[dict, StageRecord]:
    """Run an LLM stage once per module shard and merge the results.

    Falls back to a single ``run_llm_stage`` call if the full payload fits
    within ``SHARD_THRESHOLD_CHARS`` (most projects will never shard).

    After merging, the cross-shard ``check`` is run on the full merged result.
    If it fails, the error message names the stage so repair is possible at the
    caller level (manual intervention or re-run).

    Usage notes
    -----------
    - Each shard gets a ``module`` filter hint in its payload; the prompt must
      instruct the model to only emit items for the given module.
    - The merged result always carries ``schema_version`` from the first shard.
    - ``attempts`` in the returned ``StageRecord`` is the *maximum* attempts
      across all shards (1 = no repairs, 2 = at least one shard needed repair).
    """
    if len(compact(full_payload)) <= SHARD_THRESHOLD_CHARS or len(shards) <= 1:
        return run_llm_stage(
            client, number=number, name=name, file=file, payload=full_payload, check=check
        )

    merged_items: list[dict] = []
    schema_version: str | None = None
    max_attempts = 1
    all_usages: list[UsageInfo] = []
    combined_digests: list[str] = []

    system = load_prompt(name)

    for shard in shards:
        module_name = shard["module"]
        shard_payload = shard["shard_payload"]
        shard_user = compact(shard_payload)
        combined_digests.append(hashlib.sha256((system + shard_user).encode()).hexdigest())

        shard_result, shard_rec = run_llm_stage(
            client,
            number=number,
            name=name,
            file=f"{file}[{module_name}]",
            payload=shard_payload,
            # No cross-shard check here; we run it on the merged result below.
            check=None,
        )
        merged_items.extend(shard_result.get(merge_key, []))
        if schema_version is None:
            schema_version = shard_result.get("schema_version")
        max_attempts = max(max_attempts, shard_rec.attempts)
        all_usages.append(shard_rec.usage)

    merged = {merge_key: merged_items}
    if schema_version is not None:
        merged = {"schema_version": schema_version, **merged}

    # Run cross-shard check on the fully assembled result.
    if check is not None:
        problems = check(merged)
        if problems:
            reason = "; ".join(problems[:3])
            if len(problems) > 3:
                reason += f" (+{len(problems) - 3} more)"
            raise Stop(
                f"STOP: Stage {number} — {name} — {file} — sharded merge failed checks — {reason}",
                stage=str(number),
            )

    # Fingerprint = XOR-fold of all per-shard digests (order-independent, stable).
    xor_int = 0
    for d in combined_digests:
        xor_int ^= int(d, 16)
    combined_digest = format(xor_int, "064x")

    return merged, StageRecord(
        name, file, combined_digest, max_attempts, usage=_merge_usages(all_usages)
    )

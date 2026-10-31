"""Stage 3 (LLM): Actor -> Action -> Screen -> Result with satisfies."""

from __future__ import annotations

from ..index import CanonicalIndex
from ..llm import LLMClient
from . import StageRecord, run_llm_stage

NUMBER, NAME, FILE = 3, "user_flows", "user_flows.json"


def run(client: LLMClient, index: CanonicalIndex, arch: dict) -> tuple[dict, StageRecord]:
    payload = {
        "requirements": [
            {
                "id": rid,
                "title": r["title"],
                "statement": r["statement"],
                "roles": r["roles"],
                "preconditions": r["preconditions"],
                "postconditions": r["postconditions"],
            }
            for rid, r in index.requirements.items()
        ],
        "screens": {s: m["name"] for m in arch["modules"] for s in m["screens"]},
    }
    out, record = run_llm_stage(client, number=NUMBER, name=NAME, file=FILE, payload=payload)
    return {"schema_version": "1", **out}, record

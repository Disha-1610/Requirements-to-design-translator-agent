"""Stage 4 (LLM): functional UI specification."""

from __future__ import annotations

from ..index import CanonicalIndex
from ..llm import LLMClient
from . import StageRecord, run_llm_stage

NUMBER, NAME, FILE = 4, "ui_spec", "ui_spec.json"


def run(
    client: LLMClient, index: CanonicalIndex, arch: dict, flows: dict
) -> tuple[dict, StageRecord]:
    payload = {
        "screens": [
            {"screen": s, "module": m["name"]} for m in arch["modules"] for s in m["screens"]
        ],
        "flows": flows["flows"],
        "requirements": [
            {
                "id": rid,
                "title": r["title"],
                "statement": r["statement"],
                "error_ids": r["error_ids"],
            }
            for rid, r in index.requirements.items()
        ],
        "data_fields": {
            e: [{"name": n, "type": f["type"], "required": f.get("required")} for n, f in fs.items()]
            for e, fs in index.entities.items()
        },
        "errors": [{"error_id": e, "name": r["name"]} for e, r in index.errors.items()],
    }
    out, record = run_llm_stage(client, number=NUMBER, name=NAME, file=FILE, payload=payload)
    return {"schema_version": "1", **out}, record

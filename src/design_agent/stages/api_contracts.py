"""Stage 5 (LLM): API contracts for stated behavior only."""

from __future__ import annotations

from ..index import CanonicalIndex
from ..llm import LLMClient
from ..validate import arch_modules, check_api_contracts
from . import StageRecord, run_llm_stage

NUMBER, NAME, FILE = 5, "api_contracts", "api_contracts.json"


def run(
    client: LLMClient, index: CanonicalIndex, arch: dict, ui: dict
) -> tuple[dict, StageRecord]:
    payload = {
        "apis": [{"api": a, "module": m["name"]} for m in arch["modules"] for a in m["apis"]],
        "screens": [
            {
                "screen": s["screen"],
                "fields": [f["name"] for f in s["fields"]],
                "satisfies": s["satisfies"],
            }
            for s in ui["screens"]
        ],
        "requirements": [
            {
                "id": rid,
                "title": r["title"],
                "statement": r["statement"],
                "preconditions": r["preconditions"],
                "assumptions": r["assumptions"],
                "error_ids": r["error_ids"],
            }
            for rid, r in index.requirements.items()
        ],
        "data_fields": {e: sorted(fs) for e, fs in index.entities.items()},
        "errors": [
            {"error_id": e, "name": r["name"], "http_status": r["http_status"]}
            for e, r in index.errors.items()
        ],
    }
    modules = arch_modules(arch)
    out, record = run_llm_stage(
        client,
        number=NUMBER,
        name=NAME,
        file=FILE,
        payload=payload,
        check=lambda o: [f.stop_line() for f in check_api_contracts(index, modules, o)],
    )
    return {"schema_version": "1", **out}, record

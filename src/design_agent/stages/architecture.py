"""Stage 2 (LLM): module ownership. Rendered to architecture.md by code."""

from __future__ import annotations

from .. import architecture_md
from ..errors import Stop
from ..index import CanonicalIndex
from ..llm import LLMClient
from . import StageRecord, run_llm_stage

NUMBER, NAME, FILE = 2, "architecture", "architecture.md"


def run(client: LLMClient, index: CanonicalIndex) -> tuple[dict, str, StageRecord]:
    payload = {
        "requirements": [
            {"id": rid, "title": r["title"], "roles": r["roles"], "epic": r["epic"]}
            for rid, r in index.requirements.items()
        ],
        "entities": sorted(index.entities),
        "actors": index.actors,
    }
    arch, record = run_llm_stage(client, number=NUMBER, name=NAME, file=FILE, payload=payload)

    owned = [e for m in arch["modules"] for e in m["entities"]]
    missing = sorted(set(index.entities) - set(owned))
    extra = sorted(set(owned) - set(index.entities))
    dupes = sorted({e for e in owned if owned.count(e) > 1})
    if missing or extra or dupes:
        raise Stop(
            f"STOP: Stage 2 — architecture — {FILE} — entity ownership — "
            f"missing {missing}, unknown {extra}, split {dupes}",
            stage="2",
        )
    return arch, architecture_md.render(arch), record

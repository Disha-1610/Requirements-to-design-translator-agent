"""Stage 2 (LLM): module ownership. Rendered to architecture.md by code."""

from __future__ import annotations

from .. import architecture_md
from ..index import CanonicalIndex
from ..llm import LLMClient
from ..validate import arch_modules, check_architecture
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
    arch, record = run_llm_stage(
        client,
        number=NUMBER,
        name=NAME,
        file=FILE,
        payload=payload,
        check=lambda out: ownership_problems(index, out),
    )
    return arch, architecture_md.render(arch), record


def ownership_problems(index: CanonicalIndex, arch: dict) -> list[str]:
    """Every data_spec entity owned exactly once; nothing owned twice (Stage 8 check 5)."""
    owned = [e for m in arch["modules"] for e in m["entities"]]
    missing = sorted(set(index.entities) - set(owned))
    extra = sorted(set(owned) - set(index.entities))
    dupes = sorted({e for e in owned if owned.count(e) > 1})
    problems: list[str] = []
    if missing or extra or dupes:
        problems.append(
            f"entity ownership — missing {missing}, unknown {extra}, split {dupes}"
        )
    # Split screens/APIs (entity splits are already reported above).
    problems += [
        f.stop_line()
        for f in check_architecture(arch_modules(arch))
        if not f.reason.startswith("entity")
    ]
    return problems

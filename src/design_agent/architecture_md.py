"""Render and parse architecture.md. Code owns the format; the LLM only supplies data."""

from __future__ import annotations

import re

_NONE = "(none)"
_PIPE = re.compile(r"(?<!\\)\|")


def _cell(items: list[str]) -> str:
    return ", ".join(items) if items else _NONE


def render(arch: dict) -> str:
    rows = []
    for m in arch["modules"]:
        owns = (
            f"screens: {_cell(m['screens'])}; APIs: {_cell(m['apis'])}; "
            f"entities: {_cell(m['entities'])}"
        )
        note = m["boundary_note"].replace("|", "\\|")
        rows.append(f"| {m['name']} | {owns} | {note} |")
    return (
        "# Architecture\n\n"
        f"## System boundary\n\n{arch['system_boundary']}\n\n"
        f"## Frontend / backend split\n\n{arch['frontend_backend_split']}\n\n"
        "## Modules\n\n"
        "| module | owns (screens/APIs/entities) | boundary note |\n"
        "|---|---|---|\n" + "\n".join(rows) + "\n"
    )


def _split_list(text: str) -> list[str]:
    text = text.strip()
    return [] if text == _NONE else [t.strip() for t in text.split(",") if t.strip()]


def parse(text: str) -> dict[str, dict[str, list[str]]]:
    """Return {module: {screens, apis, entities}}. Raise ValueError on bad structure."""
    modules: dict[str, dict[str, list[str]]] = {}
    in_modules = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_modules = line.strip() == "## Modules"
            continue
        if not in_modules or not line.startswith("|"):
            continue
        cells = [c.strip() for c in _PIPE.split(line.strip().strip("|"))]
        if len(cells) != 3 or cells[0] in ("module", "---") or set(cells[0]) == {"-"}:
            continue
        m = re.fullmatch(r"screens: (.*); APIs: (.*); entities: (.*)", cells[1])
        if not m:
            raise ValueError(f"unparseable owns cell for module {cells[0]!r}")
        if cells[0] in modules:
            raise ValueError(f"duplicate module {cells[0]!r}")
        modules[cells[0]] = {
            "screens": _split_list(m.group(1)),
            "apis": _split_list(m.group(2)),
            "entities": _split_list(m.group(3)),
        }
    if not modules:
        raise ValueError("no module table found")
    return modules

"""Stage 9 (code): diagrams are a renderer, not a designer.

Mermaid source is generated from the validated Design Package only. Labels reuse
exact package names/IDs. Output is supplementary and never modifies the six files.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.esm.min.mjs"

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px;color:#1b1b1b}}
pre.mermaid{{background:#fff}}details{{margin-top:16px}}pre{{overflow:auto}}</style>
</head><body><h1>{title}</h1><p>{legend}</p>
<pre class="mermaid">
{source}
</pre>
<details><summary>Mermaid source</summary><pre>{source}</pre></details>
<script type="module">import mermaid from "{cdn}"; mermaid.initialize({{startOnLoad:true}});</script>
</body></html>
"""


def _q(text: str) -> str:
    return text.replace('"', "#quot;")


def architecture_mermaid(arch: dict[str, dict[str, list[str]]]) -> str:
    lines = ["flowchart LR"]
    n = 0
    for mi, (module, owns) in enumerate(arch.items()):
        lines.append(f'  subgraph m{mi}["{_q(module)}"]')
        for item in owns["screens"]:
            n += 1
            lines.append(f'    n{n}["{_q(item)}"]')
        for item in owns["apis"]:
            n += 1
            lines.append(f'    n{n}("{_q(item)}")')
        for item in owns["entities"]:
            n += 1
            lines.append(f'    n{n}[("{_q(item)}")]')
        lines.append("  end")
    return "\n".join(lines)


def user_flow_mermaid(flows: list[dict]) -> str:
    lines = ["flowchart LR"]
    actors: dict[str, list[dict]] = {}
    for f in flows:
        actors.setdefault(f["actor"], []).append(f)
    for ai, (actor, rows) in enumerate(actors.items()):
        lines.append(f'  subgraph a{ai}["{_q(actor)}"]')
        for f in rows:
            k = f["flow_id"].replace("-", "")
            lines.append(f'    {k}a["{_q(f["action"])}"]')
        lines.append("  end")
    for f in flows:
        k = f["flow_id"].replace("-", "")
        sat = ", ".join(f["satisfies"])
        lines.append(f'  {k}a -- "{_q(sat)}" --> {k}s["{_q(f["screen"])}"]')
        lines.append(f'  {k}s --> {k}r(["{_q(f["result"])}"])')
    return "\n".join(lines)


def write_diagram(out_dir: Path, name: str, title: str, legend: str, source: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    mmd = out_dir / f"{name}.mmd"
    page = out_dir / f"{name}.html"
    mmd.write_text(source + "\n", encoding="utf-8")
    page.write_text(
        _PAGE.format(
            title=html.escape(title),
            legend=html.escape(legend),
            source=html.escape(source),
            cdn=MERMAID_CDN,
        ),
        encoding="utf-8",
    )
    return [mmd, page]


def render_all(design_dir: Path, out_dir: Path) -> tuple[list[Path], list[str]]:
    """Render both diagrams. One failure never blocks the other. Returns (files, STOP lines)."""
    from . import architecture_md

    written: list[Path] = []
    stops: list[str] = []
    jobs = (
        (
            "architecture",
            "Architecture",
            "Rounded: APIs. Cylinder: entities. Rectangle: screens. Grouped by owning module.",
            lambda: architecture_mermaid(
                architecture_md.parse((design_dir / "architecture.md").read_text(encoding="utf-8"))
            ),
            "architecture.md",
        ),
        (
            "user_flow",
            "User flows",
            "Swimlane = actor. Edge label = satisfies IDs. Terminal node = result.",
            lambda: user_flow_mermaid(
                json.loads((design_dir / "user_flows.json").read_text(encoding="utf-8"))["flows"]
            ),
            "user_flows.json",
        ),
    )
    for name, title, legend, build, source_file in jobs:
        try:
            written += write_diagram(out_dir, name, title, legend, build())
        except Exception as e:  # report and continue with the other diagram
            stops.append(f"STOP: Stage 9 — {name} — {source_file} — render error — {e}")
    return written, stops

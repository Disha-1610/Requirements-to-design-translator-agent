"""Stage 1: completeness sub-check and canonical index. Pure code, no LLM.

Parse once, reference forever: every later stage reads this index only.
Shape checks only; never judges requirement quality.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .constants import BR_RE, BRD_SECTIONS
from .errors import Stop
from .verify import Inputs, schema_issues

_LIST_MARK = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_STRIP_TAIL = re.compile(r"\s+[—–-]\s+|\s*\(|:")


@dataclass
class CanonicalIndex:
    requirements: dict[str, dict]
    br_ids: set[str]
    errors: dict[str, dict]
    entities: dict[str, dict[str, dict]]
    fixtures: set[str]
    transitions: dict[str, list[dict]]
    out_of_scope: list[str]
    actors: list[str]
    links: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    @property
    def functional_ids(self) -> list[str]:
        return [r for r in self.requirements if r.startswith("F") and not r.startswith("NF")]

    def to_json(self) -> dict:
        return {
            "requirements": sorted(self.requirements),
            "business_rules": sorted(self.br_ids),
            "errors": sorted(self.errors),
            "entities": {e: sorted(f) for e, f in self.entities.items()},
            "fixtures": sorted(self.fixtures),
            "actors": self.actors,
            "links": self.links,
            "out_of_scope": self.out_of_scope,
        }


def _section_pattern(num: int, title: str) -> re.Pattern[str]:
    words = r"\s+".join(re.escape(w) for w in title.split())
    return re.compile(rf"^\s*(?:#{{1,6}}\s*)?(?:\*\*)?{num}\s*\.\s*(?:\*\*)?\s*{words}", re.I | re.M)


def check_brd_sections(brd: str) -> None:
    for num, title in BRD_SECTIONS.items():
        if not _section_pattern(num, title).search(brd):
            raise Stop(f"STOP: Incomplete input — BRD.md missing Section {num}", stage="1")


def extract_out_of_scope(brd: str) -> list[str]:
    start = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?5\s*\.\s*2\b", re.M)
    end = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:5\s*\.\s*3\b|6\s*\.\s*[A-Za-z])", re.M)
    m = start.search(brd)
    if not m:
        return []
    rest = brd[m.end() :]
    e = end.search(rest)
    body = rest[: e.start()] if e else rest
    items: list[str] = []
    for line in body.splitlines():
        if not _LIST_MARK.match(line):
            continue
        text = _LIST_MARK.sub("", line).replace("*", "").strip()
        head = _STRIP_TAIL.split(text)[0].strip().lower()
        if len(head) >= 4:
            items.append(head)
    return items


def check_shape(inputs: Inputs) -> None:
    """Required-field presence for the three JSON inputs (Stage 1 completeness)."""
    _, frd_inc = schema_issues("frd.json", inputs.frd)
    _, spec_inc = schema_issues("data_spec.json", inputs.data_spec)
    _, err_inc = schema_issues("error_catalogue.json", inputs.errors)

    def missing_of(e) -> list[str]:  # noqa: ANN001
        # jsonschema emits one `required` error per missing property.
        m = re.match(r"^'(.*)' is a required property$", e.message)
        return [m.group(1)] if m else [p for p in e.validator_value if p not in e.instance]

    def collect(errs, fmt):  # noqa: ANN001, ANN202
        lines = [fmt(e, m) for e in errs for m in missing_of(e)]
        if lines:
            more = f" (+{len(lines) - 1} more)" if len(lines) > 1 else ""
            raise Stop(lines[0] + more, stage="1")

    def rec_id(e, records, key):  # noqa: ANN001, ANN202
        idx = e.absolute_path[0] if e.absolute_path else None
        if isinstance(idx, int) and isinstance(records[idx], dict) and key in records[idx]:
            return records[idx][key]
        return f"#{idx}"

    collect(
        frd_inc,
        lambda e, m: (
            f"STOP: Incomplete input — frd.json — "
            f"{rec_id(e, inputs.frd, 'requirement_id')} missing {m}"
        ),
    )

    def spec_line(e, m):  # noqa: ANN001, ANN202
        if not e.absolute_path:
            return f"STOP: Incomplete input — data_spec.json missing {m}"
        path = ""
        for p in e.absolute_path:
            path += f"[{p}]" if isinstance(p, int) else f".{p}"
        return f"STOP: Incomplete input — data_spec.json missing {path.lstrip('.')}.{m}"

    collect(spec_inc, spec_line)
    collect(
        err_inc,
        lambda e, m: (
            f"STOP: Incomplete input — error_catalogue.json — "
            f"{rec_id(e, inputs.errors, 'error_id')} missing {m}"
        ),
    )


def build_index(inputs: Inputs) -> CanonicalIndex:
    check_brd_sections(inputs.brd)
    check_shape(inputs)

    requirements: dict[str, dict] = {}
    for rec in inputs.frd:
        rid = rec["requirement_id"]
        if rid in requirements:
            raise Stop(
                f"STOP: Malformed input — frd.json — duplicate requirement_id {rid}", stage="1"
            )
        requirements[rid] = rec

    errors: dict[str, dict] = {}
    for rec in inputs.errors:
        eid = rec["error_id"]
        if eid in errors:
            raise Stop(
                f"STOP: Malformed input — error_catalogue.json — duplicate error_id {eid}", stage="1"
            )
        errors[eid] = rec

    entities: dict[str, dict[str, dict]] = {}
    for f in inputs.data_spec["fields"]:
        entities.setdefault(f["entity"], {})[f["name"]] = f

    br_ids = set(BR_RE.findall(inputs.brd))
    for rec in requirements.values():
        br_ids.update(s for s in rec["source_ids"] if BR_RE.fullmatch(s))

    return CanonicalIndex(
        requirements=requirements,
        br_ids=br_ids,
        errors=errors,
        entities=entities,
        fixtures={fx["id"] for fx in inputs.data_spec["fixtures"]},
        transitions=inputs.data_spec["state_transitions"],
        out_of_scope=extract_out_of_scope(inputs.brd),
        actors=sorted({role for r in requirements.values() for role in r["roles"]}),
        links={
            rid: {"source_ids": list(r["source_ids"]), "error_ids": list(r["error_ids"])}
            for rid, r in requirements.items()
        },
    )

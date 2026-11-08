"""Stage 8: structural validation. Pure code, no LLM. All 12 checks, none merged.

Structural and referential only. This never judges semantic fidelity.

`check_baseline` runs the input-only subset (checks 4, 10, 11, 12 against the
inputs) right after Stage 1, so a dangling reference is caught before any
LLM tokens are spent. `validate_dir` runs all 12 against a produced package.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from . import architecture_md
from .constants import DERIVED_FIELDS, OUTPUT_FILES
from .index import CanonicalIndex
from .normalize import field_variants, norm_entity
from .schemas import load_schema

CHECK_NAMES = {
    1: "files exist and JSON valid",
    2: "required fields present",
    3: "satisfies IDs exist in baseline",
    4: "ERR IDs exist in error_catalogue.json",
    5: "module ownership",
    6: "field origin in data_spec.json",
    7: "entity exists in data_spec.json",
    8: "Golden Thread coverage",
    9: "architecture items appear in artifacts",
    10: "foreign key targets exist",
    11: "scope boundary, BRD 5.2",
    12: "fixture IDs exist",
}


@dataclass(frozen=True)
class Failure:
    check: int
    file: str
    ident: str
    reason: str

    def stop_line(self) -> str:
        return (
            f"STOP: Stage 8 — check {self.check} ({CHECK_NAMES[self.check]}) — "
            f"{self.file} — {self.ident} — {self.reason}"
        )


# ---------- helpers ----------


def _spec_entity_map(index: CanonicalIndex) -> dict[str, str]:
    return {norm_entity(e): e for e in index.entities}


def fk_target_exists(index: CanonicalIndex, ref: str) -> bool:
    entity, _, fld = ref.partition(".")
    real = _spec_entity_map(index).get(norm_entity(entity))
    if real is None:
        return False
    want = field_variants(fld)
    return any(field_variants(f) & want for f in index.entities[real])


def _walk_keys(obj: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_walk_keys(v))
    elif isinstance(obj, list):
        for v in obj:
            keys.extend(_walk_keys(v))
    return keys


def _spec_field_variants(index: CanonicalIndex) -> set[str]:
    out: set[str] = set()
    for fields in index.entities.values():
        for name in fields:
            out |= field_variants(name)
    return out


def _is_known_field(index: CanonicalIndex, name: str, spec_vars: set[str]) -> bool:
    return bool(field_variants(name) & (spec_vars | DERIVED_FIELDS))


def _id_suggestion(rid: str, index: CanonicalIndex) -> str:
    for known in index.requirements:
        if known.lower() == rid.lower():
            return f"case mismatch, baseline has {known}"
    return "not in baseline"


# ---------- input-only checks (also run pre-LLM) ----------


def check_baseline(index: CanonicalIndex) -> list[Failure]:
    out: list[Failure] = []
    # 4: frd error_ids
    for rid, rec in index.requirements.items():
        for eid in rec["error_ids"]:
            if eid not in index.errors:
                out.append(Failure(4, "frd.json", f"{rid}/{eid}", "not in error_catalogue.json"))
    # 10: data_spec FKs
    for entity, fields in index.entities.items():
        for name, spec in fields.items():
            ref = spec.get("foreign_key")
            if ref and not fk_target_exists(index, ref):
                out.append(
                    Failure(10, "data_spec.json", f"{entity}.{name}", f"references missing {ref}")
                )
    # 11: scope
    for rid, rec in index.requirements.items():
        hay = f"{rec['title']} {rec['statement']}".lower()
        for item in index.out_of_scope:
            if item in hay:
                out.append(
                    Failure(11, "frd.json", rid, f"implements out-of-scope item '{item}' (BRD.md 5.2)")
                )
    # 12: fixtures in transitions
    for entity, transitions in index.transitions.items():
        for t in transitions:
            for fx in t.get("fixtures", []):
                if fx not in index.fixtures:
                    out.append(
                        Failure(
                            12,
                            "data_spec.json",
                            fx,
                            f"used in {entity} {t['from']}->{t['to']} but not in fixtures",
                        )
                    )
    return out


# ---------- per-artifact checks (run right after each LLM stage, and in validate_dir) ----------

Arch = dict[str, dict[str, list[str]]]


def arch_modules(arch: dict) -> Arch:
    """Stage 2 output {"modules": [...]} -> the {module: {screens, apis, entities}} form."""
    return {
        m["name"]: {k: list(m.get(k, [])) for k in ("screens", "apis", "entities")}
        for m in arch["modules"]
    }


def _check_ids(fails: list[Failure], index: CanonicalIndex, file: str, label: str, ids: list[str]) -> None:
    """Check 3: requirement IDs exist, exact case."""
    for rid in ids:
        if rid not in index.requirements:
            fails.append(Failure(3, file, f"{label}/{rid}", _id_suggestion(rid, index)))


def _check_errs(
    fails: list[Failure], index: CanonicalIndex, file: str, label: str, ids: list[str | None]
) -> None:
    """Check 4: ERR IDs exist in error_catalogue.json."""
    for eid in ids:
        if eid is not None and eid not in index.errors:
            fails.append(Failure(4, file, f"{label}/{eid}", "not in error_catalogue.json"))


def _owner_map(arch: Arch) -> dict[tuple[str, str], list[str]]:
    owner: dict[tuple[str, str], list[str]] = {}
    for module, owns in arch.items():
        for kind in ("screens", "apis", "entities"):
            for item in owns[kind]:
                owner.setdefault((kind, item), []).append(module)
    return owner


def _check_owner(
    fails: list[Failure],
    arch: Arch,
    owner: dict[tuple[str, str], list[str]],
    file: str,
    kind: str,
    item: str,
    module: str,
) -> None:
    """Check 5: the declared module owns the item in architecture.md."""
    if module not in arch:
        fails.append(Failure(5, file, item, f"module '{module}' not in architecture.md"))
        return
    owners = owner.get((kind, item))
    if not owners:
        fails.append(Failure(5, file, item, f"{kind[:-1]} has no owner in architecture.md"))
    elif module not in owners:
        fails.append(
            Failure(5, file, item, f"declares module '{module}', architecture.md says {owners}")
        )


def check_architecture(arch: Arch) -> list[Failure]:
    """Check 5 (no split ownership) on architecture.md."""
    return [
        Failure(5, "architecture.md", item, f"{kind[:-1]} owned by multiple modules {mods}")
        for (kind, item), mods in _owner_map(arch).items()
        if len(mods) > 1
    ]


def check_user_flows(index: CanonicalIndex, flows: dict) -> list[Failure]:
    """Check 3 on user_flows.json."""
    fails: list[Failure] = []
    for f in flows["flows"]:
        _check_ids(fails, index, "user_flows.json", f["flow_id"], f["satisfies"])
    return fails


def check_ui_spec(index: CanonicalIndex, arch: Arch, ui: dict) -> list[Failure]:
    """Checks 3, 4, 5, 6 on ui_spec.json."""
    fails: list[Failure] = []
    owner = _owner_map(arch)
    spec_vars = _spec_field_variants(index)
    for s in ui["screens"]:
        _check_ids(fails, index, "ui_spec.json", s["screen"], s["satisfies"])
        for fld in s["fields"]:
            _check_errs(fails, index, "ui_spec.json", f"{s['screen']}.{fld['name']}", fld["error_ids"])
        _check_owner(fails, arch, owner, "ui_spec.json", "screens", s["screen"], s["module"])
        for fld in s["fields"]:
            if not _is_known_field(index, fld["name"], spec_vars):
                fails.append(
                    Failure(
                        6, "ui_spec.json", f"{s['screen']}.{fld['name']}", "no match in data_spec.json"
                    )
                )
    return fails


def check_api_contracts(index: CanonicalIndex, arch: Arch, apis: dict) -> list[Failure]:
    """Checks 3, 4, 5, 6 on api_contracts.json."""
    fails: list[Failure] = []
    owner = _owner_map(arch)
    spec_vars = _spec_field_variants(index)
    for a in apis["apis"]:
        label = f"{a['method']} {a['endpoint']}"
        _check_ids(fails, index, "api_contracts.json", label, a["satisfies"])
        _check_errs(fails, index, "api_contracts.json", label, a["errors"])
        _check_owner(fails, arch, owner, "api_contracts.json", "apis", label, a["module"])
        for key in dict.fromkeys(_walk_keys(a["request"]) + _walk_keys(a["response"])):
            if not _is_known_field(index, key, spec_vars):
                fails.append(
                    Failure(6, "api_contracts.json", f"{label}/{key}", "no match in data_spec.json")
                )
    return fails


# ---------- package checks ----------


def _load_package(design_dir: Path) -> tuple[dict[str, Any], list[Failure]]:
    pkg: dict[str, Any] = {}
    fails: list[Failure] = []
    for name in OUTPUT_FILES:
        path = design_dir / name
        if not path.is_file():
            fails.append(Failure(1, name, "-", "file missing"))
            continue
        text = path.read_text(encoding="utf-8")
        if name.endswith(".json"):
            try:
                pkg[name] = json.loads(text)
            except json.JSONDecodeError as e:
                fails.append(Failure(1, name, f"line {e.lineno}", f"invalid JSON: {e.msg}"))
        else:
            try:
                pkg[name] = architecture_md.parse(text)
            except ValueError as e:
                fails.append(Failure(2, name, "-", str(e)))
    return pkg, fails


def validate_dir(design_dir: Path, index: CanonicalIndex) -> list[Failure]:
    pkg, fails = _load_package(design_dir)
    if any(f.check == 1 for f in fails):
        return fails  # cannot run the rest on a broken package

    # 2: schemas
    for name in OUTPUT_FILES[1:]:
        schema = load_schema(name.removesuffix(".json"))
        for err in Draft202012Validator(schema).iter_errors(pkg[name]):
            loc = "/".join(str(p) for p in err.absolute_path) or "-"
            fails.append(Failure(2, name, loc, err.message[:160]))
    if any(f.check == 2 for f in fails):
        return fails

    arch: dict[str, dict[str, list[str]]] = pkg["architecture.md"]
    flows = pkg["user_flows.json"]["flows"]
    screens = pkg["ui_spec.json"]["screens"]
    apis = pkg["api_contracts.json"]["apis"]
    entities = pkg["data_model.json"]["entities"]
    checklist = pkg["validation_checklist.json"]["checks"]

    fails.extend(check_architecture(arch))
    fails.extend(check_user_flows(index, pkg["user_flows.json"]))
    fails.extend(check_ui_spec(index, arch, pkg["ui_spec.json"]))
    fails.extend(check_api_contracts(index, arch, pkg["api_contracts.json"]))

    _check_ids(fails, index, "validation_checklist.json", "check", [c["requirement_id"] for c in checklist])
    for c in checklist:
        _check_errs(fails, index, "validation_checklist.json", c["requirement_id"], [c["error_id"]])
    owner = _owner_map(arch)
    for e in entities:
        _check_owner(fails, arch, owner, "data_model.json", "entities", e["name"], e["module"])

    # 7: entities exist in data_spec
    spec_entities = _spec_entity_map(index)
    for e in entities:
        if norm_entity(e["name"]) not in spec_entities:
            fails.append(Failure(7, "data_model.json", e["name"], "not in data_spec.json"))

    # 8: Golden Thread coverage
    covered: set[str] = set()
    for f in flows:
        covered.update(f["satisfies"])
    for s in screens:
        covered.update(s["satisfies"])
    for a in apis:
        covered.update(a["satisfies"])
    for rid in index.requirements:
        if rid not in covered:
            fails.append(
                Failure(8, "user_flows/ui_spec/api_contracts", rid, "absent from every satisfies array")
            )

    # 9: architecture items appear in matching artifact
    have_screens = {s["screen"] for s in screens}
    have_apis = {f"{a['method']} {a['endpoint']}" for a in apis}
    have_entities = {e["name"] for e in entities}
    for module, owns in arch.items():
        for item in owns["screens"]:
            if item not in have_screens:
                fails.append(Failure(9, "ui_spec.json", item, f"screen of {module} missing"))
        for item in owns["apis"]:
            if item not in have_apis:
                fails.append(Failure(9, "api_contracts.json", item, f"API of {module} missing"))
        for item in owns["entities"]:
            if item not in have_entities:
                fails.append(Failure(9, "data_model.json", item, f"entity of {module} missing"))

    # 10: data_model FK targets
    for e in entities:
        for fk in e["foreign_keys"]:
            if not fk_target_exists(index, fk["references"]):
                fails.append(
                    Failure(
                        10,
                        "data_model.json",
                        f"{e['name']}.{fk['field']}",
                        f"references missing {fk['references']}",
                    )
                )

    # 11 and 12 depend only on inputs
    fails.extend(f for f in check_baseline(index) if f.check in (11, 12))
    return fails

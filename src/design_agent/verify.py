"""Stage 0: input / baseline verification. Pure code, no LLM. Fail closed.

Checks, in order: presence -> frozen baseline -> strict JSON parse -> type shape.
A file that fails strict parsing is treated like a missing file. No repair.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from .baseline import verify_baseline
from .constants import REQUIRED_INPUTS
from .errors import Stop
from .schemas import load_schema

_SCHEMA_FOR = {
    "frd.json": "frd",
    "data_spec.json": "data_spec",
    "error_catalogue.json": "error_catalogue",
}


@dataclass
class Inputs:
    brd: str
    frd: list[dict]
    data_spec: dict
    errors: list[dict]
    baseline: dict = field(default_factory=dict)


def fmt_path(prefix: str, path: Any) -> str:
    out = prefix
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


def _strict_loads(text: str, name: str) -> Any:
    def _reject(constant: str) -> None:
        raise ValueError(f"non-standard JSON constant {constant}")

    try:
        return json.loads(text, parse_constant=_reject)
    except json.JSONDecodeError as e:
        raise Stop(
            f"STOP: Malformed input — {name} — {e.msg} (line {e.lineno}, col {e.colno})",
            stage="0",
        ) from e
    except ValueError as e:
        raise Stop(f"STOP: Malformed input — {name} — {e}", stage="0") from e


def _unwrap(data: Any, name: str, key: str) -> Any:
    """Accept a bare array or {key: [...]} for list-shaped inputs."""
    if isinstance(data, dict) and key in data:
        return data[key]
    if isinstance(data, list):
        return data
    raise Stop(
        f"STOP: Malformed input — {name} — expected an array or an object with '{key}'",
        stage="0",
    )


def _short(message: str, limit: int = 160) -> str:
    return message if len(message) <= limit else message[: limit - 3] + "..."


def schema_issues(name: str, instance: Any) -> tuple[list[ValidationError], list[ValidationError]]:
    """Split schema errors: `required` => incomplete (Stage 1); everything else => malformed."""
    validator = Draft202012Validator(load_schema(_SCHEMA_FOR[name].removesuffix(".json")))
    errors = sorted(validator.iter_errors(instance), key=lambda e: [str(p) for p in e.path])
    incomplete = [e for e in errors if e.validator == "required"]
    malformed = [e for e in errors if e.validator != "required"]
    return malformed, incomplete


def stage0(input_dir: Path, allow_unfrozen: bool = False) -> Inputs:
    if not input_dir.is_dir():
        raise Stop(f"STOP: Missing input — {', '.join(REQUIRED_INPUTS)}", stage="0")

    missing = [n for n in REQUIRED_INPUTS if not (input_dir / n).is_file()]
    if missing:
        raise Stop(f"STOP: Missing input — {', '.join(missing)}", stage="0")

    baseline = verify_baseline(input_dir, allow_unfrozen)

    brd = (input_dir / "BRD.md").read_text(encoding="utf-8")
    if not brd.strip():
        raise Stop("STOP: Malformed input — BRD.md — file is empty", stage="0")

    parsed = {n: _strict_loads((input_dir / n).read_text(encoding="utf-8"), n) for n in _SCHEMA_FOR}
    frd = _unwrap(parsed["frd.json"], "frd.json", "requirements")
    errors = _unwrap(parsed["error_catalogue.json"], "error_catalogue.json", "errors")
    data_spec = parsed["data_spec.json"]
    if not isinstance(data_spec, dict):
        raise Stop("STOP: Malformed input — data_spec.json — expected a JSON object", stage="0")

    for name, instance in (
        ("frd.json", frd),
        ("data_spec.json", data_spec),
        ("error_catalogue.json", errors),
    ):
        malformed, _ = schema_issues(name, instance)
        if malformed:
            first = malformed[0]
            where = fmt_path(name.removesuffix(".json"), first.absolute_path)
            raise Stop(
                f"STOP: Malformed input — {name} — {where}: {_short(first.message)}", stage="0"
            )

    return Inputs(brd=brd, frd=frd, data_spec=data_spec, errors=errors, baseline=baseline)

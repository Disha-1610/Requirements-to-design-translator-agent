"""Pipeline orchestration. Stages run sequentially; each file is written immediately.

Run folders are never overwritten: every run gets a fresh `run-YYYY-MM-DD-NN`.
Failed runs keep their folder and a run_metadata.json recording the STOP.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import __version__, architecture_md, diagrams
from .baseline import sha256_file
from .constants import OUTPUT_FILES, REQUIRED_INPUTS
from .errors import Stop
from .index import CanonicalIndex, build_index
from .llm import LLMClient
from .stages import api_contracts, data_model, ui_spec, user_flows, validation_checklist
from .stages import architecture as architecture_stage
from .validate import Failure, check_baseline, validate_dir
from .verify import stage0


def prepare(input_dir: Path, allow_unfrozen: bool = False) -> tuple[CanonicalIndex, dict]:
    """Stage 0 + Stage 1 + input-only Stage 8 checks. No LLM. Raises Stop."""
    inputs = stage0(input_dir, allow_unfrozen)
    index = build_index(inputs)
    failures = check_baseline(index)
    if failures:
        raise Stop("\n".join(f.stop_line() for f in failures), stage="8")
    return index, inputs.baseline


def new_run_dir(out_root: Path) -> Path:
    raw = out_root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    for n in range(1, 1000):
        path = raw / f"run-{day}-{n:02d}"
        try:
            path.mkdir()  # atomic: fails if it exists, so a run is never overwritten
        except FileExistsError:
            continue
        return path
    raise Stop("STOP: Run folder — could not allocate a new run directory")


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@dataclass
class RunResult:
    run_dir: Path
    status: str
    stage8: list[Failure] = field(default_factory=list)
    stage9_stops: list[str] = field(default_factory=list)


def run(
    input_dir: Path,
    out_root: Path,
    client: LLMClient,
    allow_unfrozen: bool = False,
) -> RunResult:
    run_dir = new_run_dir(out_root)
    design = run_dir / "design"
    design.mkdir()
    meta: dict = {
        "tool": "design-agent",
        "tool_version": __version__,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "llm": {
            "provider": client.name,
            "model": client.model,
            "temperature": client.temperature,
        },
        "inputs_sha256": {
            n: sha256_file(input_dir / n) for n in REQUIRED_INPUTS if (input_dir / n).is_file()
        },
        "stages": [],
        "status": "running",
    }
    try:
        index, baseline = prepare(input_dir, allow_unfrozen)
        meta["baseline"] = baseline
        _write_json(run_dir / "canonical_index.json", index.to_json())

        arch, arch_md, rec = architecture_stage.run(client, index)
        (design / "architecture.md").write_text(arch_md, encoding="utf-8")
        meta["stages"].append(rec.__dict__)
        arch_modules = architecture_md.parse(arch_md)

        flows, rec = user_flows.run(client, index, arch)
        _write_json(design / "user_flows.json", flows)
        meta["stages"].append(rec.__dict__)

        ui, rec = ui_spec.run(client, index, arch, flows)
        _write_json(design / "ui_spec.json", ui)
        meta["stages"].append(rec.__dict__)

        apis, rec = api_contracts.run(client, index, arch, ui)
        _write_json(design / "api_contracts.json", apis)
        meta["stages"].append(rec.__dict__)

        _write_json(design / "data_model.json", data_model.build(index, arch_modules))
        _write_json(design / "validation_checklist.json", validation_checklist.build(index, ui))

        failures = validate_dir(design, index)
        _write_json(
            run_dir / "stage8_report.json",
            {
                "passed": not failures,
                "failures": [f.__dict__ | {"stop": f.stop_line()} for f in failures],
            },
        )
        if failures:
            raise Stop("\n".join(f.stop_line() for f in failures), stage="8")

        files, stops = diagrams.render_all(design, run_dir / "diagrams")
        meta["diagram_files"] = [str(p.relative_to(run_dir)) for p in files]
        meta["stage9_stops"] = stops
        meta["status"] = "complete"
        return RunResult(run_dir, "complete", stage9_stops=stops)
    except Stop as stop:
        meta["status"] = "stopped"
        meta["stop"] = {"stage": stop.stage, "message": stop.message}
        raise
    finally:
        meta["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        _write_json(run_dir / "run_metadata.json", meta)


def promote(run_dir: Path, out_root: Path, version: str, approved_by: str) -> Path:
    """Human step: copy a Stage-8-passed run's six files into approved/<version>/."""
    report = run_dir / "stage8_report.json"
    if not report.is_file() or not json.loads(report.read_text())["passed"]:
        raise Stop("STOP: Promote — run has no passing Stage 8 report")
    target = out_root / "approved" / version
    if target.exists():
        raise Stop(f"STOP: Promote — approved/{version} already exists; never overwritten")
    target.mkdir(parents=True)
    for name in OUTPUT_FILES:
        shutil.copy2(run_dir / "design" / name, target / name)
    _write_json(
        target / "promotion.json",
        {
            "source_run": run_dir.name,
            "approved_by": approved_by,
            "promoted_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    )
    return target

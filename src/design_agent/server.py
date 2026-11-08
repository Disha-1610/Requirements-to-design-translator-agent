"""FastAPI backend server for the Requirements-to-Design Translator Agent UI.

Endpoints:
- GET  /              : Serves the single-page HTML / CSS / JS UI.
- POST /api/generate  : Accepts 4 specification files + optional Anthropic API key,
                        runs the deterministic design agent pipeline, and returns
                        the 6 output files and metadata.
- POST /api/download  : Accepts the same inputs and directly streams back a .zip archive.
"""

from __future__ import annotations

import io
from pathlib import Path
import tempfile
import zipfile
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from design_agent.constants import OUTPUT_FILES, REQUIRED_INPUTS
from design_agent.errors import Stop
from design_agent.llm import AnthropicClient, ReplayClient
from design_agent.runner import run

app = FastAPI(title="Requirements-to-Design Agent UI", version="0.1.0")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
INDEX_HTML = Path(__file__).parent / "static" / "index.html"

# Mount examples directory so users can load sample files with 1 click
if (ROOT_DIR / "examples").is_dir():
    app.mount("/examples", StaticFiles(directory=str(ROOT_DIR / "examples")), name="examples")


@app.get("/", response_class=HTMLResponse)
async def get_index() -> str:
    if INDEX_HTML.is_file():
        return INDEX_HTML.read_text(encoding="utf-8")
    return "<h1>Design Agent UI is starting up...</h1>"


def _process_run(
    files: list[UploadFile],
    api_key: str | None,
    model: str,
    replay_mode: bool,
) -> tuple[Path, dict]:
    """Saves uploaded files to a temp directory, executes pipeline, returns (design_dir, meta)."""
    file_map = {f.filename: f for f in files if f.filename}
    missing = [req for req in REQUIRED_INPUTS if req not in file_map]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required specification files: {', '.join(missing)}",
        )

    temp_dir = tempfile.mkdtemp(prefix="design_run_")
    temp_path = Path(temp_dir)
    in_dir = temp_path / "input"
    out_dir = temp_path / "out"
    in_dir.mkdir(parents=True, exist_ok=True)

    for name in REQUIRED_INPUTS:
        contents = file_map[name].file.read()
        (in_dir / name).write_bytes(contents)

    if replay_mode:
        root_dir = Path(__file__).resolve().parent.parent.parent
        replay_dir = root_dir / "examples" / "happy-path" / "replay"
        client = ReplayClient(replay_dir)
    else:
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Anthropic API Key is required unless demo/replay mode is enabled.",
            )
        client = AnthropicClient(model=model, api_key=api_key)

    try:
        result = run(in_dir, out_dir, client, allow_unfrozen=True)
        design_dir = result.run_dir / "design"
        meta_file = result.run_dir / "run_metadata.json"
        metadata = {}
        if meta_file.is_file():
            import json
            metadata = json.loads(meta_file.read_text(encoding="utf-8"))
        return design_dir, metadata
    except Stop as stop_err:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Validation Gate Halted",
                "stage": stop_err.stage,
                "message": stop_err.message,
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline execution error: {type(exc).__name__}: {exc}",
        )


@app.post("/api/generate")
async def generate_design(
    files: Annotated[list[UploadFile], File(description="Upload the 4 required input files")],
    api_key: Annotated[str | None, Form()] = None,
    model: Annotated[str, Form()] = "claude-3-7-sonnet-20250219",
    replay_mode: Annotated[bool, Form()] = False,
):
    design_dir, metadata = _process_run(files, api_key, model, replay_mode)

    artifacts: dict[str, str] = {}
    for filename in OUTPUT_FILES:
        filepath = design_dir / filename
        if filepath.is_file():
            artifacts[filename] = filepath.read_text(encoding="utf-8")

    return {
        "status": "success",
        "artifacts": artifacts,
        "metadata": metadata,
    }


@app.post("/api/download")
async def download_design_zip(
    files: Annotated[list[UploadFile], File(description="Upload the 4 required input files")],
    api_key: Annotated[str | None, Form()] = None,
    model: Annotated[str, Form()] = "claude-3-7-sonnet-20250219",
    replay_mode: Annotated[bool, Form()] = False,
):
    design_dir, _ = _process_run(files, api_key, model, replay_mode)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename in OUTPUT_FILES:
            filepath = design_dir / filename
            if filepath.is_file():
                zf.write(filepath, arcname=filename)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=design_package.zip"},
    )

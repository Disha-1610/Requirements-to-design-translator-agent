import json
import shutil
from pathlib import Path

import pytest

from design_agent.llm import ReplayClient
from design_agent.runner import run

ROOT = Path(__file__).resolve().parent.parent
HAPPY_INPUT = ROOT / "examples" / "happy-path" / "input"
REPLAY_DIR = ROOT / "examples" / "happy-path" / "replay"
NEGATIVE = ROOT / "examples" / "negative"


@pytest.fixture
def replay():
    return ReplayClient(REPLAY_DIR)


@pytest.fixture
def happy_run(tmp_path, replay):
    """A completed happy-path run. Returns the RunResult."""
    return run(HAPPY_INPUT, tmp_path / "out", replay)


@pytest.fixture
def design_copy(tmp_path, happy_run):
    """A mutable copy of the happy-path design/ folder."""
    dst = tmp_path / "design_copy"
    shutil.copytree(happy_run.run_dir / "design", dst)
    return dst


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

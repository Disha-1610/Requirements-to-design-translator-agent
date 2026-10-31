"""The mutation suite: every negative case must stop at its expected gate, before any LLM call."""

import json

import pytest

from design_agent.errors import Stop
from design_agent.runner import prepare

from .conftest import HAPPY_INPUT, NEGATIVE

CASES = sorted(p for p in NEGATIVE.iterdir() if p.is_dir())


def test_case_count():
    assert len(CASES) == 14  # 15 profiles minus the happy path, which has its own test


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_negative_case_stops_at_expected_gate(case):
    expected = json.loads((case / "expected.json").read_text())
    with pytest.raises(Stop) as info:
        prepare(case / "input")
    assert info.value.message.startswith(expected["expected_stop_prefix"]), info.value.message


def test_happy_inputs_pass_gates():
    index, baseline = prepare(HAPPY_INPUT)
    assert baseline["approved"] is True
    assert set(index.requirements) == {"F1", "F2", "F3", "NF1"}
    assert index.out_of_scope == [
        "cryptocurrency trading",
        "loan origination",
        "international wire transfers",
    ]


def test_unfrozen_inputs_rejected(tmp_path):
    import shutil

    dst = tmp_path / "in"
    shutil.copytree(HAPPY_INPUT, dst)
    (dst / "baseline.json").unlink()
    with pytest.raises(Stop) as info:
        prepare(dst)
    assert info.value.message.startswith("STOP: Unapproved input")
    assert prepare(dst, allow_unfrozen=True)[1]["bypassed"] is True


def test_tampered_input_rejected(tmp_path):
    import shutil

    dst = tmp_path / "in"
    shutil.copytree(HAPPY_INPUT, dst)
    (dst / "BRD.md").write_text((dst / "BRD.md").read_text() + "\nedited after freeze\n")
    with pytest.raises(Stop) as info:
        prepare(dst)
    assert "hash differs" in info.value.message

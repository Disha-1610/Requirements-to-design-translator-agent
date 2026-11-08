"""Frozen-baseline manifest. A human freezes inputs; Stage 0 verifies the freeze.

The original pipeline relied on a shared 'approved' folder. A standalone tool
cannot trust a folder name, so approval is a manifest of SHA-256 hashes written
by `design-agent freeze` and checked on every run.

Reproducible timestamps
-----------------------
``freeze()`` normally stamps ``frozen_at`` with the current UTC time.  When the
environment variable ``SOURCE_DATE_EPOCH`` is set (a standard reproducible-builds
variable, see <https://reproducible-builds.org/specs/source-date-epoch/>), the
epoch value is used instead.  CI scripts should set it so that regenerating
fixtures with ``make_negative.py`` produces byte-for-byte identical output and
``git diff --exit-code`` can detect *real* content changes rather than timestamp
noise.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from .constants import BASELINE_FILE, REQUIRED_INPUTS
from .errors import Stop


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now_iso() -> str:
    """Return the current UTC time as ISO-8601, or a fixed timestamp when
    ``SOURCE_DATE_EPOCH`` is set (reproducible-builds convention)."""
    epoch_str = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch_str is not None:
        try:
            ts = datetime.fromtimestamp(int(epoch_str), tz=UTC)
        except (ValueError, OverflowError, OSError):
            ts = datetime.now(UTC)
    else:
        ts = datetime.now(UTC)
    return ts.isoformat(timespec="seconds")


def freeze(input_dir: Path, version: str, approved_by: str) -> Path:
    files = {n: sha256_file(input_dir / n) for n in REQUIRED_INPUTS if (input_dir / n).is_file()}
    manifest = {
        "approved": True,
        "version": version,
        "approved_by": approved_by,
        "frozen_at": _now_iso(),
        "files": files,
    }
    out = input_dir / BASELINE_FILE
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out


def verify_baseline(input_dir: Path, allow_unfrozen: bool) -> dict:
    """Return baseline info for run metadata. Raise Stop if unapproved."""
    path = input_dir / BASELINE_FILE
    if not path.is_file():
        if allow_unfrozen:
            return {"approved": False, "bypassed": True}
        raise Stop(
            f"STOP: Unapproved input — {BASELINE_FILE} not found "
            "(run `design-agent freeze` or pass --allow-unfrozen)",
            stage="0",
        )
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Stop(f"STOP: Malformed input — {BASELINE_FILE} — {e.msg}", stage="0") from e
    if manifest.get("approved") is not True:
        raise Stop(f"STOP: Unapproved input — {BASELINE_FILE} — approved is not true", stage="0")
    files = manifest.get("files", {})
    for name in REQUIRED_INPUTS:
        want = files.get(name)
        if want is None:
            raise Stop(f"STOP: Unapproved input — {name} — not listed in {BASELINE_FILE}", stage="0")
        if sha256_file(input_dir / name) != want:
            raise Stop(
                f"STOP: Unapproved input — {name} — hash differs from frozen baseline", stage="0"
            )
    return {
        "approved": True,
        "version": manifest.get("version"),
        "approved_by": manifest.get("approved_by"),
        "bypassed": False,
    }

"""Command line interface. Exit codes: 0 ok, 2 STOP, 1 unexpected error."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .baseline import freeze
from .errors import Stop
from .llm import AnthropicClient, LLMClient, ReplayClient
from .runner import prepare, promote, run
from .validate import validate_dir

DEFAULT_MODEL = "claude-sonnet-5-5"


def _client(args: argparse.Namespace) -> LLMClient:
    if args.llm == "replay":
        if not args.replay_dir:
            raise Stop("STOP: Usage — --llm replay requires --replay-dir")
        return ReplayClient(Path(args.replay_dir))
    model = args.model or os.environ.get("DESIGN_AGENT_MODEL", DEFAULT_MODEL)
    return AnthropicClient(model=model, temperature=args.temperature)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="design-agent", description=__doc__)
    p.add_argument("--version", action="version", version=f"design-agent {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("freeze", help="Write baseline.json (human approval of the four inputs)")
    f.add_argument("input_dir")
    f.add_argument("--version", dest="baseline_version", required=True)
    f.add_argument("--approved-by", required=True)

    v = sub.add_parser("verify", help="Stage 0 + Stage 1 + input-only Stage 8 checks (no LLM)")
    v.add_argument("input_dir")
    v.add_argument("--allow-unfrozen", action="store_true")

    r = sub.add_parser("run", help="Full pipeline, Stages 0-9")
    r.add_argument("input_dir")
    r.add_argument("--out", required=True)
    r.add_argument("--llm", choices=("anthropic", "replay"), default="anthropic")
    r.add_argument("--model")
    r.add_argument("--temperature", type=float, default=0.0)
    r.add_argument("--replay-dir")
    r.add_argument("--allow-unfrozen", action="store_true")

    c = sub.add_parser("validate", help="Stage 8 on an existing design/ folder")
    c.add_argument("design_dir")
    c.add_argument("--input", dest="input_dir", required=True)
    c.add_argument("--allow-unfrozen", action="store_true")

    pr = sub.add_parser("promote", help="Copy a passing run to approved/<version>/ (human step)")
    pr.add_argument("run_dir")
    pr.add_argument("--out", required=True)
    pr.add_argument("--version", dest="approved_version", required=True)
    pr.add_argument("--approved-by", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "freeze":
            path = freeze(Path(args.input_dir), args.baseline_version, args.approved_by)
            print(f"Frozen: {path}")
        elif args.cmd == "verify":
            index, _ = prepare(Path(args.input_dir), args.allow_unfrozen)
            print(f"OK: {len(index.requirements)} requirements, {len(index.errors)} errors, "
                  f"{len(index.entities)} entities")
        elif args.cmd == "run":
            result = run(Path(args.input_dir), Path(args.out), _client(args), args.allow_unfrozen)
            print(f"Run complete: {result.run_dir}")
            for line in result.stage9_stops:
                print(line)
        elif args.cmd == "validate":
            index, _ = prepare(Path(args.input_dir), args.allow_unfrozen)
            failures = validate_dir(Path(args.design_dir), index)
            if failures:
                raise Stop("\n".join(f.stop_line() for f in failures), stage="8")
            print("Stage 8 PASS")
        elif args.cmd == "promote":
            target = promote(
                Path(args.run_dir), Path(args.out), args.approved_version, args.approved_by
            )
            print(f"Promoted: {target}")
    except Stop as stop:
        print(stop.message, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

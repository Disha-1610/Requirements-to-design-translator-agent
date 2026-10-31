# Contributing

## Ground rules

1. **Rules live in code, not prose.** If a prompt says "never invent X", there must be a Stage 8 check or a stage post-check that fails when X appears.
2. **Fail closed.** A gate that cannot decide stops the run with an exact `STOP:` line. No warnings-and-continue.
3. **Mechanical beats generative.** If a stage is a direct transformation of fixed data, write it in code (see Stages 6 and 7).
4. **No live API calls in tests.** Use `ReplayClient` with recorded stage outputs.
5. **Never add `_no`, `_num` or `_code` to the suffix-strip list** in `constants.py`. They collapse distinct concepts.

## Workflow

```bash
pip install -e ".[dev]"
ruff check .
pytest
python examples/make_negative.py   # after changing inputs or mutations
```

Adding a Stage 8 check: add a `Failure` producer in `validate.py`, a name in `CHECK_NAMES`, one positive and one negative test in `tests/test_stage8_checks.py`.

Adding a negative case: add a mutation to `examples/make_negative.py`, regenerate, and `tests/test_negative_cases.py` picks it up.

Commit style: imperative subject, one logical change per commit.

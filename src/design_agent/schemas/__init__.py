"""JSON Schemas shipped with the package."""

import json
from functools import cache
from importlib import resources


@cache
def load_schema(name: str) -> dict:
    """Load `<name>.schema.json` from the package."""
    text = resources.files(__package__).joinpath(f"{name}.schema.json").read_text(encoding="utf-8")
    return json.loads(text)

"""Stage 6 (code): data_spec.json -> data_model.json. Mechanical, no invention.

Allowed transformations: required -> NOT NULL flag, stated foreign_key -> FK,
source type -> database type. Nothing is added because two entities "seem related".
Unspecified `required` stays null instead of being guessed.

Foreign-key cardinality
-----------------------
`relationships[].kind` in data_model.schema.json specifies `kind: "many-to-one"`.
If cardinality is specified in data_spec (e.g. `fk_cardinality`), we accept it or
default to "many-to-one", while `foreign_keys` keeps the schema contract (`field`, `references`).
"""

from __future__ import annotations

from ..errors import Stop
from ..index import CanonicalIndex

NUMBER, NAME, FILE = 6, "data_model", "data_model.json"

_TYPE_MAP = {
    "integer": "INTEGER",
    "int": "INTEGER",
    "number": "NUMERIC",
    "decimal": "NUMERIC",
    "float": "DOUBLE PRECISION",
    "boolean": "BOOLEAN",
    "bool": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMPTZ",
    "timestamp": "TIMESTAMPTZ",
}

_DEFAULT_CARDINALITY = "many-to-one"


def db_type(spec: dict) -> str:
    src = spec["type"].lower()
    if src in ("string", "text", "str"):
        length = spec.get("length")
        return f"VARCHAR({length})" if length else "TEXT"
    return _TYPE_MAP.get(src, spec["type"].upper())


def build(index: CanonicalIndex, arch_modules: dict[str, dict[str, list[str]]]) -> dict:
    owner = {e: m for m, owns in arch_modules.items() for e in owns["entities"]}
    entities = []
    for entity, fields in index.entities.items():
        if entity not in owner:
            raise Stop(
                f"STOP: Stage 6 — data_model — {FILE} — {entity} — no owning module in architecture.md",
                stage="6",
            )
        fks = [
            {"field": n, "references": f["foreign_key"]}
            for n, f in fields.items()
            if f.get("foreign_key")
        ]
        entities.append(
            {
                "name": entity,
                "module": owner[entity],
                "fields": [
                    {
                        "name": n,
                        "source_type": f["type"],
                        "db_type": db_type(f),
                        "required": f.get("required"),
                    }
                    for n, f in fields.items()
                ],
                "primary_key": [n for n, f in fields.items() if f.get("primary_key")],
                "foreign_keys": fks,
                "relationships": [
                    {
                        "from": f"{entity}.{fk['field']}",
                        "to": fk["references"],
                        "kind": fields[fk["field"]].get("fk_cardinality") or _DEFAULT_CARDINALITY,
                    }
                    for fk in fks
                ],
            }
        )
    return {"schema_version": "1", "entities": entities}

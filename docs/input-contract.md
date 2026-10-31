# Input contract

Four files plus a freeze manifest. Schemas live in `src/design_agent/schemas/`.

| File | Shape |
|---|---|
| `BRD.md` | Headings for Sections 1 to 10 (`## 7. Requirements` or `7.Requirements`). Out-of-scope items are bullets under 5.2. |
| `frd.json` | Array, or `{"requirements": [...]}`. 15 fields per record (see `frd.schema.json`). `requirement_id` matches `F<n>` or `NF<n>`. |
| `data_spec.json` | `{"fields": [...], "state_transitions": {...}, "fixtures": [...]}` |
| `error_catalogue.json` | Array, or `{"errors": [...]}`. `error_id`, `name`, `http_status`, `user_message`, `notes`. |
| `baseline.json` | Written by `design-agent freeze`. SHA-256 per file plus `approved: true`. |

## data_spec.json details (assumptions to confirm)

The upstream spec lists `name, type, format, length, example` per field. This tool also needs to know which entity a field belongs to and how entities relate, so the contract adds:

- `entity` (required): owning entity name.
- `required` (optional, boolean): becomes NOT NULL. Absent stays `null`; never guessed.
- `primary_key` (optional, boolean).
- `foreign_key` (optional): `"Entity.field"`. The only source of relationships.
- Transitions: `{"Account": [{"from": "PENDING", "to": "ACTIVE", "trigger": "...", "fixtures": ["ACC-001"]}]}`
- Fixtures: `[{"id": "ACC-001", ...}]`

If your upstream format differs, write a small adapter that emits this shape before freezing.

## STOP messages

```
STOP: Missing input — <filename[, filename]>
STOP: Unapproved input — <detail>
STOP: Malformed input — <filename> — <parser or type error>
STOP: Incomplete input — BRD.md missing Section <n>
STOP: Incomplete input — frd.json — <id> missing <field>
STOP: Incomplete input — data_spec.json missing <part>
STOP: Incomplete input — error_catalogue.json — <id> missing <field>
STOP: Stage <n> — <stage> — <file> — <detail>
STOP: Stage 8 — check <n> (<name>) — <file> — <id/field> — <reason>
STOP: Stage 9 — <diagram> — <source file> — <diagnostic> — <reason>
```

Exit code 2 on any STOP. Stage 9 STOPs are reported but do not invalidate a Stage 8 pass.

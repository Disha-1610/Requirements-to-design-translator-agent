# Input requirements

Put these files in one folder. File order does not matter. If any rule below fails, the run stops with a `STOP:` message and no design is produced.

## 1. `BRD.md`

- Headings for all ten sections, numbered, in this form: `## 7. Requirements` or `7.Requirements`.

  1 Introduction, 2 Project Drivers, 3 Constraints, Assumptions and Dependencies, 4 Current State, 5 Scope of Work, 6 Business Rules, 7 Requirements, 8 Business Implementation Requirements, 9 Issues, 10 Handover
- Business rules written as `BR-001`, `BR-002`, ...
- Out-of-scope items as bullet points under `5.2 Out of Scope for v1`.

## 2. `frd.json`

A list of requirements, or `{"requirements": [...]}`. Every record needs all 15 fields:

`requirement_id`, `official_id`, `title`, `statement`, `epic`, `source_ids`, `roles`, `preconditions`, `postconditions`, `error_ids`, `assumptions`, `open_question_ids`, `priority`, `status`, `version`

- `requirement_id` looks like `F1` (functional) or `NF1` (non-functional). IDs are case-sensitive and unique.
- `source_ids`, `roles`, `preconditions`, `postconditions`, `error_ids`, `assumptions`, `open_question_ids` are lists (empty is fine).
- `error_ids` look like `ERR-001` and must exist in `error_catalogue.json`.

## 3. `data_spec.json`

An object with three parts:

- `fields`: list. Each field needs `entity`, `name`, `type`. Optional: `format`, `length`, `example`, `required`, `primary_key`, `foreign_key` (`"Entity.field"`).
- `state_transitions`: object, one list per entity. Each item has `from`, `to`, and optional `trigger`, `fixtures`.
- `fixtures`: list. Each item has an `id` such as `CUST-001`. Every fixture used in a transition must be listed here.

## 4. `error_catalogue.json`

A list of errors, or `{"errors": [...]}`. Every error needs:

`error_id`, `name`, `http_status` (number, 100 to 599), `user_message`, `notes`

## 5. `baseline.json` (approval)

Created by a human with:

```bash
design-agent freeze ./inputs --version v1 --approved-by "Your Name"
```

Editing any input after freezing makes the run stop. Re-freeze after approved changes.

## Check before running

```bash
design-agent verify ./inputs
```

Runs input checks only. No LLM, no cost.

Full detail and all STOP messages: [docs/input-contract.md](docs/input-contract.md).

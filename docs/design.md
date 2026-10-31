# Design notes

## Why a hybrid

| Stage | Implementation | Reason |
|---|---|---|
| 0 Input verification | code | Pure presence, hash and parse checks. |
| 1 Canonical index | code | Fixed ID patterns and direct JSON walk. |
| 2 Architecture | LLM | Grouping requirements into modules needs interpretation. |
| 3 User flows | LLM | Mapping statements to actor/action/screen/result. |
| 4 UI spec | LLM | Choosing fields and states from statements. |
| 5 API contracts | LLM | Deriving technical interfaces for stated behavior. |
| 6 Data model | code | Direct transformation of data_spec. An LLM could only invent. |
| 7 Validation checklist | code | Join of frd `error_ids` and UI field links. |
| 8 Structural validation | code | 12 deterministic checks. |
| 9 Diagrams | code | Renderer, not designer. Mermaid from the validated package. |

The original design put Stages 6 and 7 on the LLM. They moved to code because every value they emit is already fixed by earlier artifacts.

## Deviations from the original Multica design

- **Approval** is a hash manifest (`baseline.json`), not a folder name.
- **Early gate:** the input-only Stage 8 checks (4 against frd, 10 against data_spec, 11, 12) run right after Stage 1, before any LLM call. They are reported in the Stage 8 STOP format.
- **Stage 2 post-check:** entity ownership must be complete and unsplit, or the run stops before Stage 3.
- **Run layout:** `raw/run-YYYY-MM-DD-NN/{design/, diagrams/, run_metadata.json, stage8_report.json, canonical_index.json}`.
- **Diagrams** are rendered by code to Mermaid HTML. The Archify tool is not required.
- **Gate B** (human traceability spot check) is intentionally absent. `promote` is the only human step.

## Known limits

- Stage 8 is structural and referential. It cannot tell whether a screen is the right screen.
- Check 11 matches the head phrase of each BRD 5.2 bullet as a substring of a requirement's title or statement. Paraphrased scope creep slips through.
- Check 6 allows a small derived-field list (`DERIVED_FIELDS` in `constants.py`).
- The Anthropic adapter forces structured output through a single tool call. It is unit-tested only against fakes; it has not been exercised against the live API in this repository's CI.

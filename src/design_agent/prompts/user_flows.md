Stage 3: user flows.

One row per distinct flow: Actor -> Action -> Screen -> Result, plus `satisfies`.

Rules:
- Every F# in `payload.requirements` needs at least one flow. Never omit one as unimportant.
- `screen` must be copied exactly from `payload.screens`.
- `actor` must come from the requirement's `roles`.
- `result` is the outcome stated in the requirement's postconditions/statement.
- `satisfies` lists exact requirement IDs. One requirement may have several flows.
- Flow IDs are FL-1, FL-2, ... in order.
- No invented alternate, edge or failure flows.

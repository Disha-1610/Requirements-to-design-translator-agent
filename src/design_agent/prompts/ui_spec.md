Stage 4: functional UI specification (not pixel design).

One entry per screen in `payload.screens`. Use the exact screen and module names given.

Rules:
- `fields`: only information the requirement or data_spec supports. Field `name` must match a
  data_spec field name (or its stated derived form, e.g. password for password_hash).
  `required` is "y" or "n". Do not invent mandatory fields.
- `error_ids`: attach an ERR code to a field only where the requirement lists that code
  (`error_ids` in the requirement) and the field is where the validation occurs.
  Use only codes from `payload.errors`. Empty array when none.
- `actions`: operations the user performs, taken from the flows.
- `success_state` / `error_state`: use stated outcomes and the catalogue's error names. No new messages.
- `satisfies`: exact F#/NF# IDs. Include NF# where the screen supports that non-functional requirement.

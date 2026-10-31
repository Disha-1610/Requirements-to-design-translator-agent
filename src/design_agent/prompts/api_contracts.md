Stage 5: API contracts.

One entry per API in `payload.apis` ("METHOD /path"). Split into `method` and `endpoint`,
and use the module the architecture assigns.

Rules:
- `request` / `response`: objects mapping field name -> type. Field names must trace to data_spec
  fields (or standard derived fields: tokens, status, totals).
- `auth`: only what the inputs state (preconditions/assumptions). If nothing is stated, "none".
- `errors`: ERR codes from `payload.errors` that the requirement lists for this behavior. No new codes.
- `satisfies`: exact F#/NF# IDs the API implements, including relevant NF#.
- Derive technical interfaces for stated behavior only. No new business operations.

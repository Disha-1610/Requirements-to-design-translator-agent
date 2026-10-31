Stage 2: application architecture (ownership only).

Produce: system_boundary, frontend_backend_split, and modules.
Each module owns screens, APIs and entities, with a one-line boundary_note.

Rules:
- Group requirements into modules by the functionality they state. No module for unsupported functionality.
- `entities`: every entity in `payload.entities` must be owned by exactly one module. Use the exact names. No others.
- `screens`: name the screens implied by the requirements. Each screen is owned by exactly one module.
- `apis`: name each backend interaction as exactly "METHOD /path". Each is owned by exactly one module.
- External actors/systems named in requirements are outside the boundary.
- Not a solution architecture: no tech stack, deployment, dependency graph or ADR.
- Later stages must reuse these names verbatim, so choose them once and carefully.

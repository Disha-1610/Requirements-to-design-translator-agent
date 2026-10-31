# design-agent

Requirements-to-design translator with traceability guarantees.

Four approved documents in. Six design artifacts out. Every artifact keeps its source IDs (`BR-###`, `F#`, `NF#`, `ERR-###`), so one business rule can be followed to a screen, an API, a data field and an error code.

> Status: alpha (v0.1). It translates requirements. It does not audit them, write code or generate tests.

## Pipeline

```
BRD.md  frd.json  data_spec.json  error_catalogue.json  (+ baseline.json)
   Stage 0  inputs present, frozen, strict-parsed              code
   Stage 1  completeness check, canonical ID index             code
   Stage 2  architecture.md                                    LLM
   Stage 3  user_flows.json                                    LLM
   Stage 4  ui_spec.json                                       LLM
   Stage 5  api_contracts.json                                 LLM
   Stage 6  data_model.json                                    code
   Stage 7  validation_checklist.json                          code
   Stage 8  12 structural checks (Golden Thread, FKs, scope)   code
   Stage 9  diagrams/architecture.html, user_flow.html         code
```

Rules are enforced in code, not trusted to the prompt. Examples: every `ERR-###` in any output must exist in the catalogue; every `satisfies` ID must exist with exact case; every F#/NF# must appear in at least one `satisfies` array; every foreign key must resolve.

## Quickstart

```bash
pip install -e ".[anthropic]"
export ANTHROPIC_API_KEY=...

design-agent freeze ./inputs --version v1 --approved-by "Your Name"
design-agent verify ./inputs                       # Stages 0, 1 and early Stage 8, no LLM
design-agent run ./inputs --out ./out              # full pipeline
design-agent promote ./out/raw/run-<date>-01 --out ./out --version v1.0 --approved-by "Your Name"
```

No API key? Run the bundled example with recorded stage outputs:

```bash
design-agent run examples/happy-path/input --out ./out \
  --llm replay --replay-dir examples/happy-path/replay
```

Output layout (a run is never overwritten):

```
out/raw/run-2026-10-31-01/
├── design/            six canonical files
├── diagrams/          Mermaid HTML, supplementary
├── canonical_index.json
├── stage8_report.json
└── run_metadata.json  model, temperature, input hashes, prompt hashes
```

## What it refuses to do

It stops with an exact `STOP:` line (exit code 2) on a missing, unapproved, malformed or incomplete input, a dangling reference, an out-of-scope requirement or a broken Golden Thread. It never repairs input and never invents business rules, entities, fields or error codes. See [docs/input-contract.md](docs/input-contract.md).

## Test matrix

14 negative cases plus the happy path live in `examples/negative/` and `examples/happy-path/`.

| Case | Mutation | Stops at |
|---|---|---|
| TC-MISS-01..04 | Drop one input | Stage 0 |
| TC-MALF-01..02 | Broken JSON, unparsable type | Stage 0 |
| TC-INC-01..04 | Missing sections/fields/blocks | Stage 1 |
| TC-CONT-01 | `ERR-999` not in catalogue | Stage 8 check 4, before any LLM call |
| TC-CONT-02 | Foreign key to `AccountX` | Stage 8 check 10, before any LLM call |
| TC-CONT-03 | Crypto trading, out of scope in BRD 5.2 | Stage 8 check 11, before any LLM call |
| TC-CONT-04 | Fixture `CUST-999` undefined | Stage 8 check 12, before any LLM call |
| TC-HAPPY-01 | Clean inputs | Full run, Stage 8 PASS |

```bash
pytest   # replay LLM only, never touches the network
```

## Reproducibility

Pin the model (`--model` or `DESIGN_AGENT_MODEL`), temperature defaults to 0. Each run records provider, model, temperature, SHA-256 of every input and of each stage prompt in `run_metadata.json`. LLM output is still not guaranteed byte-identical across runs; Stage 8 guarantees structure and traceability, not wording.

## Limits

See [docs/design.md](docs/design.md). The main ones: Stage 8 is structural, scope matching is phrase-based, and the live Anthropic adapter is not covered by CI.

## License

Apache-2.0. See [LICENSE](LICENSE). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md). Vulnerabilities: [SECURITY.md](SECURITY.md).

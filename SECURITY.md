# Security

## Reporting

Report vulnerabilities privately through GitHub Security Advisories on this repository. Do not open a public issue for a vulnerability. Expect an acknowledgement within a week.

## Scope notes

- The tool reads local input files and writes local run folders. It makes network calls only through the configured LLM provider.
- Requirement documents are sent to the LLM provider in Stages 2 to 5. Do not run it on confidential requirements with a provider you do not trust.
- API keys are read from the provider's standard environment variable (`ANTHROPIC_API_KEY`). The tool never writes keys to run folders or metadata.
- `baseline.json` is an integrity check (SHA-256), not authentication. Anyone who can edit the inputs can re-freeze them.
- Diagram pages load Mermaid from a pinned jsdelivr URL. Vendor it if you need offline or locked-down use.

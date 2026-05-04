# Partner Integration

`companyctx` is a deterministic context-routing muscle for downstream
workflows. The contract is simple: one site in, one schema-locked JSON
envelope out.

This page is the canonical integration reference. It replaces the need
to infer the contract from scattered examples and research notes.

## What `companyctx` guarantees today

- The CLI emits one top-level envelope:
  `{schema_version, status, data, provenance, error?}`.
- `status` is the only branch point you need:
  `ok`, `partial`, or `degraded`.
- `error` is structured when `status != "ok"`:
  `{code, message, suggestion}`.
- The schema is strict (`extra="forbid"`) and versioned via
  `schema_version`.
- Providers never raise at the boundary. Failures become envelope state,
  not crashes.

## What is shipped now

- Zero-key Attempt 1: `site_text_trafilatura`
- Smart-proxy Attempt 2: `smart_proxy_http`
- Direct-API Attempt 3 for reviews: `reviews_google_places`
- SQLite cache / Vertical Memory: default cached reads plus
  `--refresh`, `--from-cache`, `--no-cache`, `cache list`, `cache clear`

What that means in practice:

- `data.pages.*` is the default populated bucket.
- `data.reviews` can populate when `GOOGLE_PLACES_API_KEY` is configured.
- `data.social`, `data.signals`, and `data.mentions` remain mostly null
  today.

## What remains downstream

`companyctx` does not do:

- prompt orchestration
- synthesis
- scoring or ranking
- CRM writes
- agent memory beyond the local cache
- people/contact enrichment

Those belong in the workflow consuming the envelope.

## Integration pattern

Minimal CLI integration:

```bash
companyctx fetch acme-bakery.com --json
```

Minimal Python integration:

```python
import json
import subprocess

result = subprocess.run(
    ["companyctx", "fetch", "acme-bakery.com", "--json"],
    capture_output=True,
    text=True,
    check=False,
)
env = json.loads(result.stdout)

if env["status"] == "ok":
    data = env["data"]
elif env["status"] == "partial":
    data = env["data"]
    err = env["error"] or {}
    print(err.get("code"), err.get("message"), err.get("suggestion"))
else:
    data = None
```

## How to branch on the envelope

Use this decision rule:

- `ok`: consume all populated data normally.
- `partial`: consume whatever is populated; log or route on
  `error.code` and `error.suggestion`.
- `degraded`: treat the run as unusable for the current workflow.

Do not branch on free-text error substrings if a structured field exists.
Prefer `error.code` to `error.message`.

## Current provider truth

Today a stock install registers exactly these providers:

- `site_text_trafilatura`
- `smart_proxy_http`
- `reviews_google_places`

Everything else described in the repo is either deferred, a candidate,
or a placeholder for future measurement.

## Out of scope by design

- Hosted service behavior
- Headless-browser orchestration
- MCP server exposure
- People-data extraction
- Multi-page crawling
- Inference or scoring in the collector

## Related docs

- [`README.md`](../README.md)
- [`SCHEMA.md`](SCHEMA.md)
- [`SPEC.md`](SPEC.md)
- [`PROVIDERS.md`](PROVIDERS.md)
- [`../examples/README.md`](../examples/README.md)

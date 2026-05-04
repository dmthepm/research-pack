# SKILL.md — companyctx

**Purpose:** Extract deterministic, schema-locked company context
(tech stack, reviews, core offerings) from any B2B domain. One site in,
one JSON envelope out. Zero keys on the default path.

`companyctx = company context.` The product packages the context of a
company so an agent can reason about it, rather than reading raw HTML.

**Commands.**

- `companyctx fetch <site> --json` — run the waterfall; emit one envelope.
  Reads the local cache by default; flags: `--refresh` (force re-fetch +
  shadow-write), `--from-cache` (read-only; exit non-zero on miss),
  `--no-cache` (bypass read, still write back).
- `companyctx schema` — emit the envelope's Draft 2020-12 JSON Schema.
- `companyctx providers list --json` — registered providers as JSON
  (`slug`, `tier`, `category`, `cost_hint`, `status`, `reason`).
- `companyctx validate <path.json>` — round-trip through the Pydantic schema.
- `companyctx cache list [--json]` — latest cached envelope per host.
- `companyctx cache clear --site X` / `--older-than 7d` — prune cached
  rows (at least one filter required).

**Rules for agents.**

- Companies only. Never extract people data.
- Branch on `status` (`ok | partial | degraded`), not on try/except.
- Every envelope carries `schema_version`. v0.4 is `"0.4.0"`.
- When `status != "ok"`, `error` is a structured `{code, message, suggestion}`;
  switch on `error.code` (one of `ssrf_rejected | network_timeout |
  blocked_by_antibot | fixture_path_traversal_rejected | response_too_large |
  no_provider_succeeded | misconfigured_provider | empty_response |
  cache_corrupted`). `fixture_path_traversal_rejected` only fires on the
  `--mock` fixture path — URL-path traversal is not guarded by this code.
- Pipe stdout; don't parse logs. The JSON envelope is the contract.
- The `data.site` field is the identifier; `data.pages` holds homepage-
  derived content (`homepage_text`, `about_text`, `services`, `tech_stack`).
- `data.reviews` / `data.social` / `data.signals` / `data.mentions` are
  reserved in the schema but stay `null` today — the providers that
  fill them are deferred (see `docs/SPEC.md`). Schema-locked partials,
  not bugs.

**Envelope shape.**

```json
{
  "data": {
    "fetched_at": "2026-04-22T18:35:02.767112Z",
    "mentions": null,
    "pages": {
      "about_text": "...",
      "homepage_text": "...",
      "services": ["..."],
      "tech_stack": ["..."]
    },
    "reviews": null,
    "signals": null,
    "site": "acme-bakery.com",
    "social": null
  },
  "error": null,
  "provenance": {
    "site_text_trafilatura": {
      "cost_incurred": 0,
      "error": null,
      "latency_ms": 412,
      "provider_version": "0.1.0",
      "status": "ok"
    }
  },
  "schema_version": "0.4.0",
  "status": "ok"
}
```

**Example pipe.**

```bash
companyctx fetch acme-bakery.com --json \
  | jq '.data.pages | {services, tech_stack}'
```

See `docs/SCHEMA.md` for the full envelope, `docs/SPEC.md` for the CLI
surface (including deferred commands), and `docs/ZERO-KEY.md` for the
honest anti-bot coverage matrix.

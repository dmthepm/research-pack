# Changelog

All notable changes to `companyctx` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed — BREAKING (envelope schema)

- **Renamed `path_traversal_rejected` → `fixture_path_traversal_rejected`
  in the `EnvelopeError.code` Literal.** The prior code name implied the
  validator guarded URL-path traversal (`example.com/../etc/passwd`);
  it never did — the code only fires for `--mock` fixture-slug escapes.
  Agents pattern-matching on the old string must switch to the new one.
  No new code was introduced; the behavior is unchanged. URL-path
  traversal remains out of scope — open a separate issue if a guard is
  needed. (COX-50 / #87.)
- **`schema_version` remains `"0.4.0"` on this branch.** The rename is
  schema-breaking even though the rest of the v0.4 line is already on
  `main`; `companyctx schema` output, the Pydantic `Envelope(...)`
  literal, and the fixtures corpus in this branch all advertise the
  renamed code under the current `0.4.0` envelope discriminator.

## [0.4.0] — 2026-04-23

v0.4.0 bundles the COX-52 FM-7 floor correction, the COX-49 NXDOMAIN
routing fix, and a schema-version bump that closes the drift the
v0.3.0 cache merge introduced (the `cache_corrupted` Literal was added
without bumping `SCHEMA_VERSION`).

### Changed — envelope schema bump (v0.4)

- **`schema_version` bumped to `"0.4.0"`.** The Literal set didn't
  grow in this release, but the mapping from provider input to
  `error.code` did change (COX-52 and COX-49, see below). Per the
  closed-set rule documented in `docs/SPEC.md`, any observable
  change in what `error.code` an agent can receive on the same input
  is a minor schema bump. Also closes the v0.3.0 drift: PR #93 added
  `"cache_corrupted"` to the `EnvelopeErrorCode` Literal without
  bumping `SCHEMA_VERSION`, so v0.3.0 on PyPI already advertised a
  subset of codes vs. what `main` emitted. All call sites use the
  `SCHEMA_VERSION` constant (per the COX-47 refactor in #88), so
  there are no source edits at call sites — only the constant +
  `Literal["0.4.0"]` in `companyctx/schema.py`, plus every pinned
  test and every committed `expected.json`.

### Changed — FM-7 floor correction (COX-52 / #91)

- **`EMPTY_RESPONSE_BYTES` raised 64 → 1024.** The v0.3.0 floor caught
  truly-empty bodies but not thin bodies; the v0.2 partner-integration
  validation (`research/2026-04-22-v0.2-joel-integration-validation.md`
  §3, n=209) measured `status: ok` + `<1 KiB` extracted text at **41 /
  209 = 19.6 %**, concentrated in partner-active niches (gutter
  installation 6/14, real-estate photography 5/11, virtual staging
  4/11). Those envelopes returned "partial data wearing an `ok` label"
  — the single biggest partner-breaking gap still live on a
  freshly-tagged release. v0.4.0 raises the floor so the FM-7
  thin-body class surfaces as `error.code: "empty_response"` instead
  of silent success. Retires the v0.2.0 Known Limitations disclosure
  in behavior, not just name.
- **Post-fix rate verified: 0.0 %.** Re-classifying the full 209-site
  v0.2 validation corpus against the new floor lands the post-fix
  FM-7 rate at **0 / 209** (acceptance threshold was <5 %). Analysis
  + per-niche breakdown committed as
  `research/2026-04-23-cox-52-post-fix-reclassification.md`. Not a
  live re-run (the 209-site COX-46 harness stored the byte counts the
  gate reads from; re-classification is deterministic against the
  archived data); a live re-run on fresh network is a post-tag
  follow-up if partner behavior changes.
- **Path A chosen over Path B.** Raising the existing floor preserves
  the closed Literal set for `EnvelopeErrorCode`; a separate
  `thin_response` code (Path B) was deferred to a future minor only
  if agent feedback asks for the distinction.
- **Synthetic corpus homepage template inflated.** The 30-prospect
  synthetic fixtures extracted to ~350–400 bytes on v0.3.0 — they
  would have tripped the new floor on every run. The homepage
  template in `scripts/build-fixtures.py` now carries differentiator,
  audience, and credentials prose so extraction lands comfortably
  above 1 KiB, matching the p50 of real-world sites the validation
  measured. Every committed `expected.json` in `fixtures/<synthetic>/`
  regenerated in lockstep.
- **FM-7 thin-body regression fixtures.** 19 new pseudonymized
  fixtures under `fixtures/fm7-thin-*/`, each with a `homepage.html`
  that extracts to between 64 and 1024 UTF-8 bytes and an
  `expected.json` asserting the post-fix envelope shape
  (`status: degraded`, `error.code: "empty_response"`). 2 seeds each
  for the 4 thin-dominated niches (virtual staging, real-estate
  photography, gutter installation, real-estate staging) + 1 seed for
  each of 11 occasional-FM-7 niches. Pinned in `test_regression_corpus.py`
  for byte-diff regression. Recipe table lives in
  `scripts/promote-fm7-thin-fixtures.py`.

### Fixed — NXDOMAIN routing (COX-49 / #86)

- **`unsafe_url:dns_resolve_failure` now routes to
  `no_provider_succeeded`.** Pre-v0.4.0 the SSRF guardrail raised a
  bare `unsafe_url: DNS resolution failed ...` on NXDOMAIN, and the
  classifier's substring match on `unsafe_url` won before any
  DNS-specific branch — so a non-resolving host silently appeared as
  an SSRF attempt to downstream agents. Under v0.4.0 the guardrail
  tags every `UnsafeURLError` with a `category` token; provider
  wrappers emit category-prefixed strings of the shape
  `unsafe_url:<category>: <detail>`. The classifier checks for
  `unsafe_url:dns_resolve_failure` first and routes it to
  `no_provider_succeeded`. Private-IP, metadata-host, scheme, and
  parse rejections keep their existing `ssrf_rejected` routing.
  Closes #86.

### Added

- **COX-52 acceptance test suite** (`tests/test_cox52_thin_body_acceptance.py`).
  Three focused tests: a ~500-byte HTML payload through
  `site_text_trafilatura` emits `status: failed` + `error: "empty_response"`;
  the same payload through `smart_proxy_http` recovery tags the proxy row
  identically (so Attempt 2 cannot launder a thin body past the gate);
  the orchestrator envelope lands as `status: degraded` +
  `error.code: "empty_response"` + actionable `suggestion`. These
  mirror the acceptance checklist on #91 exactly.
- **COX-49 regression tests** — `tests/test_envelope_error_codes.py`
  gains `test_nxdomain_routes_to_no_provider_succeeded` (unit: the
  classifier's substring rules) and
  `test_nxdomain_cli_path_returns_no_provider_succeeded` (integration:
  a `.invalid` host through the real `site_text_trafilatura` provider
  + orchestrator lands on `no_provider_succeeded`).

## [0.3.0] — 2026-04-23

### Added — Vertical Memory cache (COX-6 / #9)

- **SQLite cache lands.** Every `fetch` run persists the assembled
  envelope to a local SQLite file under `default_cache_dir() /
  "companyctx.sqlite3"` (XDG-respecting via `platformdirs`). Subsequent
  runs against the same host serve from cache by default until the row
  expires (30-day default TTL). The cache is the Vertical Memory moat —
  the user accumulates a queryable local B2B dataset as a side effect
  of normal use.
- **Three user-domain tables + a migration ledger.** `companies` (latest
  envelope per host), `raw_payloads` (full envelope JSON per run for
  audit), `provenance` (per-provider row mirroring
  `ProviderRunMetadata`), and `schema_version` (managed by the runner).
  Migrations are first-class — numbered SQL files under
  `companyctx/migrations/NNNN_<slug>.sql` apply in ascending order at
  open time, each in its own transaction. No implicit `ALTER TABLE` at
  startup.
- **Read-key shape.** `(normalized_host, provider_set_hash)` plus TTL.
  `provider_set_hash` is a 16-char SHA-256 prefix of sorted
  `(slug, provider_version)` pairs from the live registry — bumping a
  provider's `version` invalidates stale rows automatically without an
  explicit DELETE.
- **`fetch` flags wired.** `--refresh` ignores the cached read and
  force-writes a shadow row (audit trail; old rows kept).
  `--from-cache` returns only the cached payload, never hits the
  network, and exits non-zero on miss. `--no-cache` bypasses the read
  path; the fresh result is still written back. `--from-cache` cannot
  be combined with `--refresh` or `--no-cache`.
- **`cache list` + `cache clear`.** `cache list` shows one row per
  host (text and `--json` modes). `cache clear` requires at least one
  filter (`--site` or `--older-than 7d`); wiping the entire cache is
  intentional friction (delete the DB file directly).
- **Cache writes are opportunistic.** A write failure (full disk,
  locked file) never takes a successful fetch down with it; the
  envelope is the product, persistence is opportunistic. Cache reads
  are similarly best-effort — a corrupted row falls through to a
  fresh fetch.
- **Cache failures degrade, never crash.** A cache-open failure on
  the default `fetch` path warns to stderr (under `--verbose`) and
  continues with `cache=None`; the user gets a normal envelope from
  the fresh fetch. The `--from-cache` path can't fall back to the
  network by definition, so an open or read failure there emits a
  structured envelope with the new `cache_corrupted` error code
  (`status: degraded`, `error.suggestion` points at
  `cache clear --site`). Exit code stays `2` so existing pipelines
  keep working; the structured envelope is additive.
- **`cache_corrupted` joins the `EnvelopeError.code` Literal.** Same
  closed-set rule as `empty_response`: agents branch on
  `error.code`, humans read `error.message`. Folded into the v0.3.0
  bump rather than minting a separate v0.3.1 — v0.3.0 is unreleased
  on PyPI (still at `0.2.0`), so the cumulative `[Unreleased]` block
  carries it.

### Known cache-key behavior — `--refresh` is the documented remedy

The cache key hashes `(slug, provider_version)` for **installed**
providers, not their runtime-env-configured availability. A
`smart_proxy_http` registry hashes the same whether
`COMPANYCTX_SMART_PROXY_URL` is set or not — so a cached partial
created before the env var was exported keeps winning even after
the proxy becomes available. This is deliberate: keying on env
shape would invalidate the cache every time a user toggled a shell.
The consequence is real, though, so document the workaround:
**run `companyctx fetch <site> --refresh`** when you change provider
env config and want stale partials evicted. Tracked here so future
agents don't re-litigate the design.

### Changed — envelope schema bump (v0.3)

- **`schema_version` bumped to `"0.3.0"`.** Adding the `empty_response`
  code to the closed `EnvelopeError.code` Literal is a minor schema
  bump. v0.2.0 envelopes still validate under the old Literal but the
  orchestrator now emits `"0.3.0"` on every run.
- **`Envelope.schema_version` is now required; the literal default has
  been removed.** A missing, `null`, or empty-string `schema_version` now
  fails `Envelope.model_validate_json` with a `ValidationError`, and every
  `Envelope(...)` constructor site must pass `schema_version="0.3.0"`
  explicitly. The prior default silently let pre-v0.2 envelopes (no
  `schema_version`, bare-string `error`) validate as current, defeating
  the whole point of a shape discriminator — agents saw the literal
  stamped on a stale envelope and made wrong assumptions about
  version-gated fields. The published JSON Schema (`companyctx schema`)
  now lists `schema_version` in the `required` array. Lands with the v0.3
  minor bump; downstream call sites that build envelopes programmatically
  must pass the kwarg. Closes COX-47 / #84.
- **New `empty_response` error code (COX-44 / #79).** Both waterfall
  attempts now gate on extracted-text UTF-8 byte length against
  `EMPTY_RESPONSE_BYTES = 64`. Zero-key `site_text_trafilatura`
  (Attempt 1) and the smart-proxy recovery path (Attempt 2) share the
  gate via `companyctx.extract.is_empty_response`, so a proxy that
  returns an HTTP 200 with an empty body surfaces as
  `status: "failed"`, `error: "empty_response"` on its provenance row
  instead of laundering a silent-success onto the envelope. Measuring
  UTF-8 bytes (not `len(text)`) keeps multibyte scripts from
  false-positiving as empty. The orchestrator lands
  `error.code: "empty_response"` at the envelope top level with an
  actionable suggestion. Retires the "empty-body silent-success"
  disclosure added to v0.2.0 Known Limitations. Automatic smart-proxy
  retry on an Attempt-1 empty is intentionally out of scope — the
  recovery path skips primary rows tagged `empty_response`.

### Added

- **`reviews_google_places` provider (Attempt 3, direct-API)** — COX-5 / #7.
  Resolves a site hostname via legacy Google Places Text Search, accepts
  Google's prominence-ordered first result (the legacy Text Search
  response doesn't include `website`, so picking by domain match would
  require an extra Details billing hit per candidate for no gain), and
  reads `user_ratings_total` + `rating` via Place Details. Populates
  `data.reviews.{count, rating, source="reviews_google_places"}`. Never
  raises: missing `GOOGLE_PLACES_API_KEY` → orchestrator skips invocation
  entirely (no provenance row, zero-key status stays `ok`); 401 / 403 /
  `REQUEST_DENIED` / `OVER_QUERY_LIMIT` → `status: failed` with
  `blocked_by_antibot` prefix. Cost charged in integer US cents via
  `ProviderRunMetadata.cost_incurred`: Text Search Basic ($32/1k) + Place
  Details Basic+Atmosphere ($22/1k; `rating`/`user_ratings_total` are
  Atmosphere-tier SKUs) = 6¢/happy-path; constants live in the provider
  module as tenths-of-a-cent and ceil-sum at emission. `--mock` reads a
  `fixtures/<slug>/google_places.json` file and always charges 0 cents.
  Scope stays tight to count + rating; hours / phone / categories /
  individual review text are out-of-scope per issue-7 guidance.
- **`companyctx providers list --json`** — registry introspection as a JSON
  array (one dict per provider). Columns: `slug`, `tier`
  (`zero-key` / `smart-proxy` / `direct-api`), `category`, `cost_hint`,
  `status` (`ready` / `not_configured`), `reason`. Text-mode output gains
  the same columns. Closes #68 Part B.
- **Optional `required_env` class var** on providers. `smart_proxy_http`
  declares `COMPANYCTX_SMART_PROXY_URL`; the CLI surfaces missing entries
  as `not_configured` + a human-readable reason.

### Changed

- **Orchestrator skips primary providers whose `required_env` is unmet
  — discovery path only (COX-5).** When the CLI (or any caller that
  lets us run `discover()`) finds an opt-in direct-API provider
  registered via entry points but not wired, the orchestrator skips
  invocation: no provenance row, zero-key envelope stays `ok`. Mirrors
  how the smart-proxy stays off provenance on a clean zero-key run and
  preserves the README's "Zero keys on the default path" promise.
  Callers who pass a provider set explicitly via
  `core.run(providers={...})` (library-API form) bypass this filter:
  every slug they hand us runs, and a `not_configured` row still lands
  on the envelope so the misconfiguration signal isn't silently
  dropped — the caller explicitly opted in, so we honour it.
  `providers list` surfaces unconfigured slugs either way via its
  independent env check.
- **Envelope-error suggestion routes to provider-agnostic guidance when
  `error.code == "misconfigured_provider"` (COX-5).** Prior generic
  "configure a smart-proxy provider key" suggestion misled users whose
  actual gap was a missing direct-API key (Places, Yelp, etc.). The
  specific env-var name still lives verbatim in `error.message`
  (copied from the provider's own error string); the suggestion line
  is now a tier-agnostic "configure the missing provider's env key."
  Smart-proxy suggestion wording preserved for the Attempt-1-block
  codes where it remains correct.
- **Docs honesty pass (post-v0.2-tag).** README hero envelope, status
  block, provider tables, `docs/SPEC.md`, `docs/SCHEMA.md`, `SKILL.md`,
  and every file in `examples/` now describe the actual shipped v0.2
  surface (zero-key + smart-proxy + `schema_version` + structured
  `EnvelopeError`). Reserved-but-deferred features (SQLite cache,
  `--from-cache` / `--refresh`, `batch`, direct-API providers,
  `signals_site_heuristic`, `--markdown`) are labelled with tracking
  issues. Every example's expected-output block and bash / Python
  script runs clean against `v0.2.0`. Closes #67.
- **`fetch --markdown` help text** explicitly labels the flag
  experimental + not implemented in v0.2 (already rejects at runtime).
- **Examples now resolve `fixtures/` relative to the script** instead of
  `Path("fixtures")` so `06-competitor-monitor.py`,
  `07-inbound-webhook-enrichment/main.py`, and `08-support-ticket-context.py`
  run clean from any CWD.

### Fixed — tech-stack false positives (COX-43 / #78)

- **`detect_tech_stack` tightened to high-confidence signals only.** The
  v0.2 implementation substring-matched a lowercased copy of the full
  HTML for framework names ("wordpress", "shopify", "squarespace", …)
  and emitted the tech on any hit. That crossed into inference per
  invariant #7: a third-party share-widget `<script src>` path, a
  legacy HTML comment naming a prior platform, or a blog-post sentence
  discussing website builders all fired detections the site wasn't
  actually running. The RC dogfood surfaced the diagnostic signature —
  `tech_stack: [WordPress, Shopify, Squarespace]` simultaneously on a
  single site, three mutually-exclusive platforms asserting co-presence.
- **New detector accepts three high-confidence signal classes only:**
  (1) `<meta name="generator">` declarations, (2) framework-owned asset
  hostnames / paths in *load-bearing* resource URLs (`<script src>`,
  `<link rel="stylesheet">`, `<link rel="preload" as="script|style">`,
  `<link rel="modulepreload">`) — hint-style `preconnect` /
  `dns-prefetch` and pointer-style `canonical` / `alternate` / `icon`
  links name a URL without loading it and do NOT count — and
  (3) framework-specific class tokens or `data-*` attributes on
  `<html>` / `<body>` (e.g. `wp-elementor`, `elementor-*`, `sqs-site`,
  `wix-site`, `data-wf-site`). Class-token matches require an exact
  token or a hyphen-delimited prefix so substrings like
  `content-elementor-like` don't fire.
- **`tech_stack: list[str]` shape preserved.** No schema_version bump;
  this is a detector correctness fix, not an envelope surface change.
- **FP-reproduction fixture pinned.** `fixtures/tech-fp-mentions-only/`
  carries an HTML page that mentions every detectable platform in
  prose, legacy comments, and third-party widget src URLs without
  loading any of them. The v0.2 detector emits all six; the v0.3
  detector emits `tech_stack: []`. Wired into both
  `tests/test_fixtures_corpus.py` (shape-check) and
  `tests/test_regression_corpus.py` (byte-diff regression).
- **`docs/EXTRACTION-STRATEGY.md`** gains a "Tech fingerprint
  confidence" section naming the three signal classes and the per-tech
  selectors.

## [0.2.0] — 2026-04-22

### Changed — BREAKING (envelope schema)

- **Envelope `error` changed from `str | None` to a structured
  `EnvelopeError | None`** with machine-readable `code`, human-readable
  `message`, and actionable `suggestion`. Agents branching on the old
  free-text `error` substring will need to switch to `error.code`. The
  former top-level `suggestion` field is removed; it now lives inside
  `EnvelopeError.suggestion`. SemVer-major for the envelope contract;
  SemVer-minor for the package. See COX-37 / #70.
- `error.code` is a closed Literal: `ssrf_rejected | network_timeout |
  blocked_by_antibot | path_traversal_rejected | response_too_large |
  no_provider_succeeded | misconfigured_provider`. New codes land in
  minor releases and bump `schema_version`.

### Added

- **New top-level `schema_version: Literal["0.2.0"]` envelope field.**
  Consumers can branch on shape without substring-parsing. v0.1 envelopes
  lack this field and fail validation under `extra="forbid"`.
- **`companyctx schema` CLI verb.** Dumps the envelope's Draft 2020-12 JSON
  Schema to stdout. Agents validate against our shape without importing
  `companyctx`.
- **`companyctx/py.typed` marker (PEP 561).** Ships in wheel + sdist so
  downstream `mypy` users see concrete Pydantic types instead of `Any`.
- **Public-API re-exports in `companyctx/__init__.py`.** `from companyctx
  import Envelope` (and every other public model) now works without
  reaching into `companyctx.schema`. Closes #56.

### Changed (CLI honesty — #68 Part A)

- `--from-cache` / `--refresh` / `--no-cache` / `--config` previously were
  accepted silently and ignored. They now raise `typer.BadParameter` with a
  link to the tracking issue (#9 — SQLite cache schema + migrations; the
  v0.2.0 messages originally named a phantom tracking number, corrected in
  the Unreleased block below). No silent-pass behavior for contracts the
  tool does not honour.
- `batch` / `cache list` / `cache clear` previously exited 2 with no output.
  They now print `<command> is not implemented in v0.2.0 — see #N` to
  stderr before exiting non-zero.
- Dev-dep version bounds tightened from `>=` to `~=` (compatible-release)
  for `ruff`, `mypy`, `pytest`, `pytest-cov`, `hypothesis` — matches the
  `curl_cffi` policy already in core deps.

## [0.1.0] — 2026-04-21

### Added

- **M2 envelope + orchestrator + first working provider (#15).** `companyctx
  fetch <site> --mock --json` now emits a schema-valid `Envelope` instead of
  exiting 2. Full `{status, data, provenance, error?, suggestion?}` shape per
  `docs/SPEC.md`, every model `extra="forbid"`.
- **Deterministic Waterfall orchestrator** (`companyctx/core.py`). Discovers
  providers via `importlib.metadata.entry_points("companyctx.providers")`,
  runs them in deterministic slug order, aggregates per-provider status into
  top-level `ok | partial | degraded`, attaches actionable `suggestion` on
  non-ok. Never raises at the boundary — a provider that throws still lands
  as a `failed` row.
- **First zero-key provider `site_text_trafilatura`**. Extracts
  `pages.homepage_text` / `about_text` / `services` / `tech_stack` from the
  fixture corpus (`--mock` path) and from live HTTP (Attempt 1 of the
  waterfall). Graceful-partial on 401/403/timeout.
- `companyctx providers list` walks registered entry points and prints slug /
  category / cost hint (was exit-2 stub).
- `companyctx validate <path>` round-trips a JSON file through the envelope
  (was exit-2 stub).
- `ProviderRunMetadata.cost_incurred` (int cents, default `0`) so the
  envelope can surface per-provider spend.
- `trafilatura` moved from the `[extract]` extra into core dependencies —
  zero-key text extraction is now the default install path.
- **Regression-corpus validation** (`tests/test_regression_corpus.py`). Five
  fixtures — `acme-bakery`, `coastal-fitness`, `midtown-auto`,
  `mapleridge-contractor`, `oakleaf-bakery` — are pinned as a byte-diff
  regression suite. Together they touch every detectable tech-stack branch
  plus the empty-`tech_stack` (no-markers) case across three niches. These
  are regression snapshots, not real golden oracles; the rationale + coverage
  table lives in `fixtures/README.md`.
- **`scripts/build-fixtures.py` now generates `expected.json` by running the
  orchestrator** against the just-written HTML, so the committed fixtures
  stay in lockstep with `companyctx.core.run` as regression snapshots. This
  is useful for drift detection, not as an independent oracle. All 30
  `expected.json` files regenerated to the M2 shape (raw observations in
  `pages`; non-`pages` slots null until their providers land).

### Notes / follow-ups

- TLS-impersonation library choice (issue #15 acceptance checkbox) remains
  blocked on the 10-site network spike; `decisions/2026-04-20-zero-key-stealth-strategy.md`
  stays **proposed**. The provider's `_stealth_fetch` currently uses
  `requests` + a realistic Chrome UA as a placeholder; swap to `curl_cffi`
  once the spike lands.

## [0.1.0.dev0] - 2026-04-20

First PyPI publish. Pre-release dev marker. Reserves the `companyctx` name
and validates the OIDC trusted-publisher pipeline end-to-end. Every CLI
command still exits `2` — the first working provider lands in Milestone 2.

### Added

- **PyPI trusted-publisher release pipeline.** `.github/workflows/publish.yml`
  triggers on `release: published`, builds sdist+wheel, and uploads via
  `pypa/gh-action-pypi-publish@release/v1` using short-lived OIDC — no
  long-lived PyPI token in the repo. The `publish` job is gated on a
  `pypi` GitHub Environment with Devon as required reviewer; deployments
  are restricted to `v*` tags.
- Repo scaffolding (Milestone 1): `pyproject.toml`, package skeleton, CI, docs,
  issue/PR templates, MIT license, contributor covenant.
- `fetch --refresh` and `fetch --from-cache` CLI stubs (surface only; behavior
  wired in M4 alongside the real cache). These are first-class Vertical-Memory
  flags, not afterthought `--no-cache` inversions.
- `docs/SPEC.md` snapshot now specifies the top-level
  `{status: ok | partial | degraded, data, provenance, error?, suggestion?}`
  envelope and the Deterministic Waterfall provider attempt order.
- `docs/ARCHITECTURE.md` — brains-and-muscles framing, Deterministic
  Waterfall diagram, Vertical Memory cache posture.
- `docs/SCHEMA.md` — Pydantic envelope in detail (`CompanyContext` +
  sub-models + `ProviderRunMetadata`).
- `docs/ZERO-KEY.md` — honest anti-bot coverage matrix, graceful-partial
  contract, M1 stealth-fetcher spike deliverables.
- `docs/PROVIDERS.md` — day-one provider table with cost hints,
  `SmartProxyProvider` interface shape, write-your-own-provider guide.
- In-repo `decisions/` folder with the three load-bearing ADRs:
  `2026-04-20-name-change-to-companyctx.md` (accepted),
  `2026-04-20-zero-key-stealth-strategy.md` (proposed — library choice
  pending an M1 spike), and `2026-04-20-skill-md-not-mcp.md` (accepted).
  Walks-the-walk artifact for the OSS audience.
- `SKILL.md` at the repo root — ~150-token agent-discovery surface
  (purpose, commands, rules for agents, one bash example). Noontide-wide
  posture: CLI + `SKILL.md`, not MCP.
- README rewritten around zero-key hero + IS/ISN'T values +
  Deterministic Waterfall diagram + honest coverage matrix +
  brains-and-muscles pipe example + single Main Branch breadcrumb. ISN'T
  list now includes the explicit "Not an MCP server — ever, in our
  roadmap" line.

### Changed

- **Renamed `research-pack` → `companyctx`.** GitHub repo and PyPI package.
  See `decisions/2026-04-20-name-change-to-companyctx.md` (in-repo ADR landing
  in the same M1 PR).
- **Vocabulary swap `domain` → `site` across user-facing surfaces.** CLI
  positional arg (`companyctx fetch <site>`), schema identifier field
  (`CompanyContext.site`), cache-clear option (`--site`), fixture layout
  (`fixtures/<site>/`), and all docs prose. Avoids the collision with
  "problem domain" / "domain-driven design" / "domain expertise." The
  existing `site: SiteSignals` sub-model — which held homepage-derived
  content — moves to `pages: SiteSignals` to free up `site` for the
  identifier. Internal normalized forms stay as `host` / `origin`.

### Fixed

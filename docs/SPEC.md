# SNAPSHOT — canonical at `noontide-projects/boston-v1/decisions/`; do not maintain here

> This file is a snapshot of the CLI + envelope surface. The canonical spec
> lives in the upstream design workspace under the `companyctx`
> spec-location/shape decision (schema + CLI shape) and the `companyctx`
> scope-and-brand-lock decision (output contract, Deterministic Waterfall,
> Vertical Memory, `status` enum).
>
> Shape edits land upstream and flow back via a new handoff cycle. Shipped-vs-
> deferred state (which commands / flags / providers are wired today) is
> refreshed with each release — this file is current as of `v0.4.0`.

---

# companyctx — spec (v0.4)

## Purpose

Take a prospect site, emit a structured, schema-locked JSON payload about
the **company** at that site. One downstream synthesis LLM call per prospect
reads the JSON and writes its brief — `companyctx` is the deterministic muscle
that replaces the "LLM reads HTML to extract facts" step.

The collector surfaces **observations**. Inference happens in the synthesis
layer that consumes the JSON. No people data in v0.1 (company side only).

## CLI surface

Built with Typer. Conforms to clig.dev.

Shipped today:

| Command | Behavior |
|---|---|
| `companyctx fetch <site>` | Run the Deterministic Waterfall for one site; emit one envelope. Reads the SQLite cache by default. |
| `companyctx schema` | Emit the envelope's Draft 2020-12 JSON Schema to stdout. |
| `companyctx validate <path>` | Round-trip a JSON envelope through the Pydantic schema. |
| `companyctx providers list [--json]` | Enumerate registered providers — slug, waterfall tier, category, cost hint, config status, reason. |
| `companyctx cache list [--json]` | Latest cached envelope per host (one row per host). |
| `companyctx cache clear --site X` / `--older-than 7d` | Prune cached rows; at least one filter is required. |

Reserved in the CLI surface but **not wired** yet — invoking them
prints a tracking-issue pointer to stderr and exits non-zero, so agents
don't build on a contract we don't honour yet:

| Command / flag | Why reserved | Tracking |
|---|---|---|
| `companyctx batch <csv>` | Fan-out wrapper over `fetch`; deferred to a follow-up slice now that the cache makes re-runs cheap. | #9 |

Flags on `fetch`:

- `--out <path>` — write JSON to a file instead of stdout.
- `--json` / `--markdown` — `--json` is the supported contract.
  `--markdown` is **experimental and not implemented**; the CLI rejects
  it with an explicit message so downstream pipelines don't ship a
  silent contract (#68).
- `--mock` — load from `fixtures/<site>/` instead of the network. Paired
  with `--fixtures-dir` (default `./fixtures`).
- `--verbose` — per-provider run-log to stderr.
- `--ignore-robots` — explicit CLI-only; **not** settable via TOML or env.
- `--refresh` — ignore the cached read; force-write a fresh row. Old rows
  stay (audit trail).
- `--from-cache` — return only the cached payload; never hit the network.
  Exits non-zero on miss. Cannot be combined with `--refresh` or
  `--no-cache`.
- `--no-cache` — bypass the cache read path; the fresh result is still
  written back.

Reserved but **not wired** — `fetch` rejects this with a
`typer.BadParameter` pointing at the tracking issue:

- `--config <toml>` — TOML loader still deferred (#9).

## Output contract

Every `companyctx fetch` invocation emits one envelope, regardless of whether
the run succeeded, partially succeeded, or was degraded by cache / anti-bot /
missing keys. Downstream pipelines branch on `status`, never on try/except
around a crash.

```
{
  "schema_version": "0.4.0",       // top-level shape discriminator
  "status": "ok" | "partial" | "degraded",
  "data":   CompanyContext,        // the schema payload (always present, may
                                   //   have nullable fields on partial)
  "provenance": {                  // per-field / per-provider attempt lineage
    <provider_slug>: ProviderRunMetadata,
    ...
  },
  "error": EnvelopeError | null    // structured error when status != "ok"
}
```

Status semantics:

- **`ok`** — every required provider succeeded and no per-field fallback fired.
- **`partial`** — one or more providers degraded (missing key, anti-bot block,
  timeout), but `data` is still schema-conformant. `error.code` names the
  primary cause from a closed set; `error.suggestion` names the fix.
- **`degraded`** — no provider succeeded. `error.code` names the primary
  failure; `error.suggestion` names the next action.

`EnvelopeError.code` is one of `ssrf_rejected | network_timeout |
blocked_by_antibot | fixture_path_traversal_rejected | response_too_large |
no_provider_succeeded | misconfigured_provider | empty_response |
cache_corrupted`. See `docs/SCHEMA.md` for the shape.

#### `empty_response` (v0.3, floor raised in v0.4.0)
`fixture_path_traversal_rejected` fires **only** on the `--mock` fixture
path when the slug escapes `fixtures_dir` (e.g. `companyctx fetch
"../etc/passwd" --mock`). A live fetch whose URL path contains `../`
is not guarded by this code — URL-path traversal is out of scope in
v0.4 (tracking via a follow-up issue if required). The v0.3 code name
`path_traversal_rejected` implied broader coverage than the validator
delivered; the rename in v0.4 matches the code to its actual scope.

#### `empty_response` (v0.3, floor raised in v0.4.0)

Closes the silent-success-on-empty and silent-success-on-thin gaps
called out in v0.2.0 Known Limitations. When the zero-key `site_text`
provider completes a fetch but the extracted homepage text is shorter
than `EMPTY_RESPONSE_BYTES = 1024` UTF-8 bytes (tunable in
`companyctx/extract.py`), the provider row surfaces as
`status: "failed"`, `error: "empty_response"`. The orchestrator maps
that to top-level `error.code: "empty_response"` with an actionable
suggestion (`"site returned HTTP 200 with effectively no content; try
--ignore-robots or check with a browser"`).

The 1024-byte cutoff (v0.4.0, COX-52) supersedes the v0.3.0 64-byte
floor. The v0.3.0 floor caught truly-empty bodies only; the v0.2
partner-integration validation (`research/2026-04-22-v0.2-joel-
integration-validation.md` §3, n=209) measured 41 / 209 = 19.6 % of
`status: ok` envelopes returning under 1 KiB of extracted text —
"FM-7 thin-body" — concentrated in partner-active niches. Those cases
are partial data wearing an `ok` label. v0.4.0 merges the
`empty_response` code with FM-7's thin-extract threshold so both
classes surface honestly. Re-classifying the 209-site corpus against
the new floor puts the post-fix FM-7 rate at 0 / 209
(`research/2026-04-23-cox-52-post-fix-reclassification.md`). A
legitimate one-page brochure site that clears 1 KiB stays `ok`; a
4xx-but-HTTP-200 maintenance stub or a JS-only SPA shell trips the
gate. The gate measures **UTF-8 bytes**, not character count, so
multibyte scripts (CJK, accented Latin, Cyrillic) don't false-positive
as empty.

The gate applies to **both waterfall attempts**: Attempt 1
(`site_text_trafilatura`) and Attempt 2 (smart-proxy recovery) run the
same check against the extracted homepage text. An effectively-empty
recovery body surfaces on the proxy row as
`status: "failed"`, `error: "empty_response"` so Attempt 2 can't launder
a silent-success onto the envelope.

When both attempts fail (e.g. Attempt 1 `blocked_by_antibot` →
Attempt 2 `empty_response`), `error.code` at the envelope level
reflects the **terminal** waterfall outcome, not the trigger. An
`empty_response` on any row wins the top-level code: the antibot
block was the reason to retry; the empty proxy body is what the
pipeline actually ended on. Per-provider rows still carry their own
error strings in `provenance[slug].error` for full traceability.

Automatic proxy retry on an Attempt-1 `empty_response` failure is
intentionally out of scope: the smart-proxy recovery path skips
primary rows tagged `empty_response` (the zero-key fetch already
worked — the site returned nothing, retrying through a proxy won't
invent content). Agents decide whether to retry upstream.

### `schema_version`

Every envelope carries a top-level `schema_version: Literal["0.4.0"]`.
Agents branch on shape by reading this field directly — no substring-
parsing an error string.

**The field is REQUIRED. There is no default.** A missing, `null`, or
empty-string `schema_version` fails validation at parse time with a
`ValidationError`. This is deliberate: a default value would let pre-v0.3
envelopes (which lack the field entirely, or carry the older `"0.2.0"`
literal) silently validate as current, defeating the point of a shape
discriminator. The constructor signature in `companyctx/schema.py` is the
source of truth — every call site must pass `schema_version="0.4.0"`
explicitly. Published JSON Schema (`companyctx schema`) lists
`schema_version` in the `required` array.

Adding an optional envelope field is a PATCH (no `schema_version`
bump). Any change to the closed `EnvelopeError.code` Literal — adding,
renaming, or removing — bumps `schema_version`. In the pre-1.0 (0.x)
series all three land as a MINOR bump; rename and removal are called
out as BREAKING in the CHANGELOG so downstream consumers see the break
explicitly. A mapping-only change that makes the same input land on a
different `error.code` is also a MINOR bump. Post-1.0, renames and
removals will require a MAJOR bump. Changing or removing a non-Literal
envelope field is always a MAJOR bump. v0.3.0 added the
`empty_response` and `cache_corrupted` codes to the closed set. v0.4.0
renames `path_traversal_rejected` → `fixture_path_traversal_rejected`
to match the validator's actual scope and also carries two mapping-only
changes: the COX-52 FM-7 floor raise (`empty_response` now fires at
<1024 UTF-8 bytes, not <64) and the COX-49 NXDOMAIN routing fix
(`unsafe_url:dns_resolve_failure` now routes to
`no_provider_succeeded` rather than `ssrf_rejected`). v0.1 envelopes
lack the `schema_version` field and fail validation under
`extra="forbid"` plus the required-field check.

### `providers list` output shape

The text output is human-first; the JSON output is the agent contract.
`--json` emits a list of dicts, one per registered provider:

```json
[
  {
    "slug": "site_text_trafilatura",
    "tier": "zero-key",
    "category": "site_text",
    "cost_hint": "free",
    "status": "ready",
    "reason": null
  },
  {
    "slug": "smart_proxy_http",
    "tier": "smart-proxy",
    "category": "smart_proxy",
    "cost_hint": "per-call",
    "status": "not_configured",
    "reason": "missing env: COMPANYCTX_SMART_PROXY_URL"
  }
]
```

`tier ∈ {"zero-key", "smart-proxy", "direct-api"}` reflects the Attempt
band in the waterfall. `status ∈ {"ready", "not_configured"}` is computed
at list-time from each provider's declared `required_env`; agents should
treat `not_configured` as "the provider will not run until the reason is
addressed."

## Data model (pydantic v2)

```
CompanyContext
├─ site: str                           # required — prospect hostname or URL
├─ fetched_at: datetime                # required
├─ pages: SiteSignals
│    ├─ homepage_text: str             # cleaned, extractor-agnostic
│    ├─ about_text: str | None
│    ├─ services: list[str]
│    ├─ tech_stack: list[str]          # detected, not claimed
├─ reviews: ReviewSignals | None
│    ├─ count: int
│    ├─ rating: float | None
│    ├─ source: str                    # provider slug
├─ social: SocialSignals
│    ├─ handles: dict[platform, handle]
│    ├─ follower_counts: dict[platform, int]
├─ mentions: MentionsSignals | None
│    ├─ items: list[MediaMention]      # award, press, podcast, etc.
├─ signals: HeuristicSignals           # raw observations only
│    ├─ team_size_claim: str | None    # e.g. "team of 6"
│    ├─ linkedin_employee_count: int | None   # company-page signal only
│    ├─ hiring_page_active: bool | None
│    ├─ last_funding_round: FundingRound | None
│    ├─ copyright_year: int | None
│    ├─ last_blog_post_at: datetime | None
│    ├─ tech_vs_claim_mismatches: list[str]
```

`ProviderRunMetadata` (in the top-level `provenance` dict, not on the model):

```
ProviderRunMetadata
├─ status: "ok" | "degraded" | "failed" | "not_configured"
├─ latency_ms: int
├─ error: str | None
├─ provider_version: str
├─ cost_incurred: int                  # US cents, default 0
```

The `signals` bucket carries **raw observations only**. The synthesis layer
does cross-reference inference (e.g. "team-size claim vs LinkedIn employee
count" or "WordPress detected vs custom-engineering positioning"). The
collector never computes a judgment.

Every field on `CompanyContext` is optional except `site` and `fetched_at`.
Missing providers degrade — never raise — and surface their reason via
`provenance[slug].status`. The top-level envelope's `status` aggregates these
into a single pipeline-branchable value.

In v0.2 the only Attempt-1 provider registered is `site_text_trafilatura`,
so live + `--mock` runs populate `data.pages.*` and leave `data.reviews` /
`data.social` / `data.signals` / `data.mentions` as `null`. Those slots
fill in as the direct-API and site-heuristic providers listed above
register. The envelope shape does not change.

## Provider-plugin interface

Each deterministic call class is a pluggable provider, discovered via Python
entry points:

```toml
[project.entry-points."companyctx.providers"]
site_text_trafilatura  = "companyctx.providers.trafilatura_site:Provider"
site_text_readability  = "companyctx.providers.readability_site:Provider"
site_meta_extruct      = "companyctx.providers.extruct_meta:Provider"
reviews_google_places  = "companyctx.providers.reviews_google_places:Provider"
reviews_yelp_fusion    = "companyctx.providers.yelp_fusion:Provider"
social_discovery_site  = "companyctx.providers.social_discovery:Provider"
social_counts_youtube  = "companyctx.providers.youtube_counts:Provider"
signals_site_heuristic = "companyctx.providers.site_heuristic_signals:Provider"
mentions_brave_stub    = "companyctx.providers.brave_search_stub:Provider"
```

Provider contract:

- `class Provider(ProviderBase)`
- `slug: ClassVar[str]`
- `category: ClassVar[Literal["site_text", "site_meta", "reviews", "social_discovery", "social_counts", "signals", "mentions"]]`
- `cost_hint: ClassVar[Literal["free", "per-call", "per-1k"]]`
- `def fetch(self, site: str, *, ctx: FetchContext) -> tuple[SignalsModel | None, ProviderRunMetadata]`
- Providers **never raise uncaught**. All failure modes map to
  `ProviderRunMetadata.status in {"degraded", "failed", "not_configured"}`.

Providers sit on the **Deterministic Waterfall** (see `docs/ARCHITECTURE.md`):

1. Zero-key stealth fetch first (default).
2. Smart-proxy provider (user-configured) on anti-bot block.
3. Direct-API provider (user-configured) for review/credential fields.

Every attempt maps to the same `CompanyContext` shape. Pipelines never branch
on which attempt succeeded — they branch on the envelope's `status`.

### Providers shipped in v0.3

- **`site_text_trafilatura`** (Attempt 1, zero-key). Stealth fetch via
  `curl_cffi` pinned to `impersonate="chrome146"` + `trafilatura`
  extraction + tech-stack fingerprint (WordPress / Shopify / Webflow / Wix
  / Squarespace / Elementor / WooCommerce). Populates `data.pages.*`.
  Graceful-partial on 401 / 403 / timeout.
- **`smart_proxy_http`** (Attempt 2, user-keyed, vendor-agnostic). URL-
  style HTTP proxy: user embeds credentials in
  `COMPANYCTX_SMART_PROXY_URL`; unset → `status: "not_configured"` with an
  actionable suggestion. On success the recovered bytes flow through the
  same shared extractor and populate `data.pages.*`. The named-vendor
  adapter lands after the smart-proxy vendor eval spike (#63).
- **`reviews_google_places`** (Attempt 3, direct-API). Google Places via
  `curl_cffi` + the legacy Places web-service API. Text Search resolves
  site hostname → candidate place_ids (we accept Google's prominence-
  ordered first result; the legacy Text Search response doesn't include
  `website`, so picking by domain match isn't available at that layer
  without an extra Details billing hit per candidate). Place Details
  reads `user_ratings_total` + `rating` on the chosen place_id.
  Populates `data.reviews.{count, rating, source}` only — hours / phone
  / categories / individual review text stay out-of-scope per COX-5.
  **Skips invocation entirely when `GOOGLE_PLACES_API_KEY` is unset**
  (no provenance row, no envelope status downgrade); `providers list`
  still surfaces the slug as `not_configured`. Configured but upstream
  401 / 403 / `REQUEST_DENIED` / `OVER_QUERY_LIMIT` → `status:
  "failed"` with structured error. Cost charged in integer US cents via
  `ProviderRunMetadata.cost_incurred`: Text Search Basic ($32/1k) +
  Place Details Basic+Atmosphere ($22/1k) = 6¢/happy-path.

### Providers deferred

- **`site_text_readability`** — bus-factor fallback for Attempt 1; wires
  alongside the fallback-selection logic in a future milestone.
- **`site_meta_extruct`** — JSON-LD / microdata / OpenGraph / RDFa /
  `sameAs` social-handle discovery.
- **`reviews_yelp_fusion`** (direct-API) — Yelp Fusion via `yelpapi`.
- **`social_discovery_site`** (zero-key) — BeautifulSoup + regex +
  extruct `sameAs`.
- **`social_counts_youtube`** (direct-API) — YouTube Data via
  `google-api-python-client` `channels.list` (ToS-safe). IG / FB / TikTok
  follower counts stay nullable per-provider policy.
- **`signals_site_heuristic`** (zero-key) — `copyright_year`,
  `last_blog_post_at`, `team_size_claim`.
- **`mentions_brave_stub`** (direct-API) — press / awards / podcast
  discovery. Tracking: #58.

`data.social` / `data.mentions` / `data.signals` stay `null` on live runs
and in `--mock` fixture output until their respective providers land.
`data.reviews` populates once `reviews_google_places` is configured (see
above). The envelope shape is stable regardless.

## Cache (Vertical Memory) — shipped in v0.3

Every `fetch` run persists the assembled envelope to a local SQLite file.
Subsequent runs against the same host serve from cache by default until
the row expires.

- **Storage.** SQLite at `default_cache_dir() / "companyctx.sqlite3"` —
  XDG-compliant via `platformdirs`. Linux: `~/.cache/companyctx/`,
  macOS: `~/Library/Caches/companyctx/`, Windows:
  `%LOCALAPPDATA%\companyctx\Cache`.
- **Tables.** `companies` (latest envelope per host),
  `raw_payloads` (full envelope JSON per run, audit-friendly),
  `provenance` (per-provider metadata mirroring `ProviderRunMetadata`),
  `schema_version` (single-row migration ledger managed by the runner).
- **Read key.** `(normalized_host, provider_set_hash)` plus TTL.
  `provider_set_hash` is a 16-char SHA-256 prefix of sorted
  `(slug, provider_version)` pairs from the **installed** registry —
  bumping a provider's `version` invalidates stale rows without an
  explicit DELETE. **Runtime-env-configured availability is NOT part
  of the key.** A `smart_proxy_http` row whose `required_env` is
  unset (`status: not_configured`) hashes the same as one whose env
  is set (`status: ready`), so a cached partial created before
  `COMPANYCTX_SMART_PROXY_URL` was exported will keep winning even
  after the proxy becomes available. This is deliberate — keying on
  env-shape would invalidate the cache every time a user toggled a
  shell — but the consequence is real: **`--refresh` is the
  documented remedy** when you change provider env config and want
  stale partials evicted. `cache list` shows what's currently
  cached; `cache clear --site <host>` evicts a single host.
- **TTL.** 30 days global default. Per-provider TTLs are M4+.
- **Migrations.** Numbered SQL files under
  `companyctx/migrations/NNNN_<slug>.sql`, applied in ascending order at
  open time, each in its own transaction. No implicit `ALTER TABLE` at
  startup.
- **Flags.** `--refresh` / `--from-cache` / `--no-cache` (see above).
- **Audit trail.** `--refresh` writes a shadow row, never replaces the
  prior one. Old rows survive until `cache clear` reaps them.

### `cache_corrupted` (v0.3)

Closes the "cache crash takes the CLI down" gap caught in code
review of #9. Cache failures must follow the same boundary contract
as provider failures — branch on `status`, never on a Python
traceback.

- **Default `fetch` path.** Cache open / read failures degrade to
  `cache=None` and the orchestrator runs providers normally. The
  envelope reflects the actual fetch outcome (`ok` / `partial` /
  `degraded` per the standard rules); no `cache_corrupted` code is
  emitted because the cache outage didn't change the user-visible
  result.
- **`--from-cache` path.** Open failure or row deserialisation
  failure (Pydantic ValidationError, JSON parse error, sqlite read
  error) emits `status: degraded` + `error.code: cache_corrupted`
  with `suggestion: "run \`companyctx cache clear --site <host>\` to
  evict the stale entry"`. Exit code stays `2` so existing
  pipelines that branch on the shell return code keep working; the
  structured envelope is additive.

A `companyctx query ...` DSL over the cache is future scope, not v0.3.

## Observability

- Structured run-log: one line per provider invocation with latency + status.
- Stderr in `--verbose`; optional log file.
- Exit code:
  - `0` — `fetch` emitted an envelope (`status: "ok" | "partial" | "degraded"`).
  - `1` — `validate` received schema-invalid JSON.
  - `2` — CLI misuse, unsupported mode, or unreadable input.
- Lightweight by design — deep transcripts belong in the downstream pipeline.

## Security and safety

- No credentials in code. All provider secrets via env or TOML config.
  `.env.example` documents required keys per provider. XDG-compliant config
  paths.
- robots.txt respected by default. `--ignore-robots` exists but must be set
  explicitly on the CLI; **not** available via TOML or env.
- No writes outside `$PWD`, `--out`, and the cache dir.

## Distribution

Python 3.10+. `pyproject.toml` + setuptools. MIT license.
`pipx install companyctx`. Dockerfile for reproducibility.
CI: ruff + mypy strict + pytest with coverage. `.claude-plugin/plugin.json`
for Claude Code marketplace compatibility.

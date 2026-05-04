# Providers

`companyctx` ships as a provider-plugin framework. Each deterministic call
class — site-text extraction, JSON-LD parsing, reviews lookup — lives in its
own provider, discovered at runtime via Python entry points under the
`companyctx.providers` group.

Providers sit on the [Deterministic Waterfall](ARCHITECTURE.md) and all return
the same envelope shape (see [`docs/SCHEMA.md`](SCHEMA.md)).

## Registered today

These are the providers a stock install can actually surface via
`companyctx providers list --json` today:

| Slug                    | Waterfall layer | Category       | Key needed                   | Cost hint | Runtime status |
|-------------------------|-----------------|----------------|------------------------------|-----------|----------------|
| `site_text_trafilatura` | Zero-key        | `site_text`    | —                            | free      | shipped |
| `smart_proxy_http`      | Smart-proxy     | `smart_proxy`  | `COMPANYCTX_SMART_PROXY_URL` | per-call  | shipped |
| `reviews_google_places` | Direct-API      | `reviews`      | `GOOGLE_PLACES_API_KEY`      | per-1k    | shipped |

`companyctx providers list` surfaces the registered set above at runtime,
annotated with each provider's local config status (`ready` /
`not_configured`).

## Candidate / deferred providers

These names are design-space placeholders or future-provider candidates,
not a promise that the modules are implemented or registered today:

| Slug                    | Waterfall layer | Category            | Current posture |
|-------------------------|-----------------|---------------------|-----------------|
| `site_text_readability` | Zero-key        | `site_text`         | bus-factor fallback candidate |
| `site_meta_extruct`     | Zero-key        | `site_meta`         | deferred |
| `social_discovery_site` | Zero-key        | `social_discovery`  | deferred |
| `signals_site_heuristic`| Zero-key        | `signals`           | deferred |
| `reviews_yelp_fusion`   | Direct-API      | `reviews`           | candidate |
| `social_counts_youtube` | Direct-API      | `social_counts`     | candidate |
| `mentions_brave_stub`   | Direct-API      | `mentions`          | stub candidate |

## The `SmartProxyProvider` interface

Attempt 2 of the Deterministic Waterfall is vendor-agnostic. We ship the
contract; the user supplies their own smart-proxy / headless-browser vendor.

```python
@runtime_checkable
class SmartProxyProvider(ProviderBase, Protocol):
    # slug / cost_hint / version inherited from ProviderBase
    category: ClassVar[Literal["smart_proxy"]]

    def fetch(
        self, url: str, *, ctx: FetchContext
    ) -> tuple[bytes | None, ProviderRunMetadata]:
        """Fetch one URL through the smart-proxy.

        Returns (response_bytes, metadata). On block/failure, returns
        (None, ProviderRunMetadata(status="failed", ...)). Never raises.
        """
        ...
```

The Protocol inherits from `ProviderBase` so the structural contract is one
chain — any future addition to `ProviderBase` propagates automatically.

The framework invokes a configured smart-proxy provider when the zero-key
fetcher returns HTTP 403 / challenge HTML / timeout. The response then flows
into the same `trafilatura` / `readability-lxml` / `extruct` chain as the
zero-key path — the schema doesn't know which layer produced the bytes.

**We don't ship a specific vendor.** Reference adapters may land as optional
extras after the measurement spike, but they're interchangeable — swap the
entry-point line in `pyproject.toml` or override at runtime.

> **Current status.** Two modules cover Attempt 2 today:
>
> - `companyctx/providers/smart_proxy_base.py` — the `SmartProxyProvider`
>   Protocol.
> - `companyctx/providers/smart_proxy_http.py` — a vendor-agnostic URL-style
>   implementation. Reads `COMPANYCTX_SMART_PROXY_URL` (full proxy URL with
>   embedded credentials) and, optionally, `COMPANYCTX_SMART_PROXY_VERIFY`
>   (path to a custom CA bundle for vendors that require one). Env-unset
>   returns `not_configured`; the top-level envelope's structured
>   `error.suggestion` names the env var. Covers any residential/datacenter
>   proxy that accepts
>   HTTP-over-CONNECT with creds folded into the URL (the 80% case).
>
> A **named reference adapter** — a shim over a specific vendor, shipped as
> an optional extra — lands after the vendor eval spike. No vendor is named
> here until that measurement is in.

## `reviews_google_places` (Attempt 3, direct-API) — shipped v0.3

Attempt 3 provider landed in COX-5. Two legacy Places API calls per
successful lookup:

1. **Text Search (Legacy)** — `textsearch/json?query=<hostname>` resolves
   the site to candidate Places.
2. **Place Details (Legacy)** — `details/json?place_id=<id>&fields=
   place_id,rating,user_ratings_total` reads the aggregate fields on the
   chosen candidate.

**Candidate picker.** The legacy Text Search response doesn't include
`website` (see Google's "Place Data Fields (Legacy)" — `website` is in
the Details Contact bundle), so we deliberately take Google's first
result (prominence ordering) and surface the `place_id` in provenance.
Verifying a pick via per-candidate Details lookups would multiply
billing with no gain over prominence for small-local-biz ICPs.

**Skip-unless-configured.** The provider only runs when
`GOOGLE_PLACES_API_KEY` is set + non-empty. Without a key the
orchestrator skips invocation entirely (no provenance row, no envelope
status downgrade); `companyctx providers list` still surfaces the slug
as `not_configured` so users see the wiring gap independently.

**Fields populated.** `data.reviews = ReviewsSignals{count, rating,
source="reviews_google_places"}`. Count and rating only — the provider
intentionally does not populate hours / categories / individual review
text. That stays out-of-scope per the COX-5 comment thread; the external
brief-pipeline downstream of companyctx reads only count + rating today.

**Failure modes (never raises).**

- Missing env → provider skipped at the orchestrator (no provenance row).
  `providers list` shows the slug as `not_configured` with an actionable
  suggestion pointing at `GOOGLE_PLACES_API_KEY`.
- HTTP 401 / 403 → `status="failed"` with `blocked_by_antibot` prefix
  (classifies into envelope `error.code="blocked_by_antibot"`).
- Places API `REQUEST_DENIED` / `OVER_QUERY_LIMIT` → same.
- Text Search `ZERO_RESULTS` → `status="failed"` naming the hostname.
- Network timeout → `status="failed"` classified as `network_timeout`.

**Cost accounting.** `ProviderRunMetadata.cost_incurred` is integer US
cents. Sourced from Google's published legacy Places pricing at COX-5
measurement time:

- Text Search (Basic): $32/1k = 3.2¢/call.
- Place Details (Basic + Atmosphere): $17 + $5 = $22/1k = 2.2¢/call.
  The `rating` + `user_ratings_total` fields sit in the Atmosphere
  bundle, not Basic.

Fractional cents are summed per leg and ceiled to an integer at
emission so partial billing never reads as free. Happy path: ceil(3.2 +
2.2) = **6 cents**. Text-Search-only (`ZERO_RESULTS` / quota) bills
ceil(3.2) = **4 cents**. Constants live as module-level integers (tenths
of a cent) in `companyctx/providers/reviews_google_places.py` — bump
them when Google changes pricing. `--mock` runs always charge 0 cents.

## Provider rules (non-negotiable)

- **Never raise uncaught.** Every failure maps to
  `ProviderRunMetadata.status in {"degraded", "failed", "not_configured"}`.
- **Declare `cost_hint`.** `"free"`, `"per-call"`, or `"per-1k"` — so
  `companyctx providers list` can surface cost before the user wires a key.
- **Env-only secrets.** No API keys in code, tests, fixtures, or TOML.
- **Respect robots.txt by default.** `--ignore-robots` exists but is
  CLI-only; not settable via TOML or env.
- **No cross-provider imports.** Providers are isolated; CI lint enforces it.
- **Schema-first.** Provider output maps to the shared `CompanyContext`
  envelope. No shape-shifting per provider.

Full rules in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Writing a new provider

1. Drop a module under `companyctx/providers/<slug>.py` with a `Provider`
   class conforming to `ProviderBase` (see `companyctx/providers/base.py`).
2. Declare `slug`, `category`, `cost_hint`, `version` as `ClassVar`s.
3. Implement `fetch(site, *, ctx: FetchContext) -> tuple[Model | None, ProviderRunMetadata]`.
   Catch everything at your boundary; never let an exception escape.
4. Register under `[project.entry-points."companyctx.providers"]` in
   `pyproject.toml`.
5. Add a unit test under `tests/` using a fixture in `fixtures/<site>/`.
   `--mock` runs must be deterministic — re-running produces byte-identical
   output modulo `fetched_at`.
6. Open a PR. Keep it narrow — one provider per PR is the norm.

Stubs for the day-one providers land in Milestone 3.

## Out-of-scope providers

- LinkedIn / Crunchbase enrichment. Out of scope — that's people-data or
  duplicates Apollo/Clearbit territory.
- IG / FB / TikTok follower-count scrapers. ToS risk; stays nullable.
- Full hosted-actor runners beyond a stub pattern. Can be added under the
  `SmartProxyProvider` interface if/when wanted.
- Brave Search / Exa / Tavily mention providers beyond the
  `not_configured` stub.
- Multi-page / sitemap crawling. One site in, one structured object out.

See also [`docs/REFERENCES.md`](REFERENCES.md) for the upstream OSS libraries
each provider wraps.

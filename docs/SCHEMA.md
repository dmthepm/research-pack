# Schema

The Pydantic v2 shape `companyctx` emits. The schema is the product — providers
are replaceable, the contract is not.

The envelope below is the v0.4.0 shape. Adding a new optional field is
backwards-compatible; removing or renaming a field — or changing the shape of
an existing one — is a schema-version bump. Always branch on the top-level
`schema_version` field to detect envelope evolution.

v0.4.0 renames `path_traversal_rejected` →
`fixture_path_traversal_rejected` to match the validator's actual scope
(the code only fires for `--mock` fixture-slug escapes; URL-path
traversal is not guarded). Renaming a code in the closed Literal is
schema-breaking; v0.4.0 is the minor bump from v0.3.0 carrying it.
v0.3.0 added two error codes to the closed `EnvelopeError.code` Literal:
`empty_response` (the silent-success-on-empty gate) and `cache_corrupted`
(emitted on `--from-cache` when the cache opens but the row can't be
deserialized). See `docs/SPEC.md` §empty_response and §cache_corrupted
for the semantics. v0.4.0 keeps the same Literal set but bumps
`SCHEMA_VERSION` for two code-mapping changes on the same input:
`empty_response` now fires at <1024 UTF-8 bytes of extracted text
(was <64 in v0.3.0; COX-52 / #91), and DNS-resolution failures route
to `no_provider_succeeded` instead of `ssrf_rejected` (COX-49 / #86).

Consumers can pull the live JSON Schema with:

```bash
companyctx schema   # Draft 2020-12 JSON Schema, no flags
```

## The envelope

Every `companyctx fetch` invocation returns one wrapper around the payload:

```python
class Envelope(BaseModel):
    schema_version: Literal["0.4.0"]    # required — no default
    status: Literal["ok", "partial", "degraded"]
    data: CompanyContext
    provenance: dict[str, ProviderRunMetadata]
    error: EnvelopeError | None = None
```

`schema_version` is **required**. A missing, `null`, or empty-string
value fails validation — a default would let pre-v0.2 envelopes silently
validate as current. See `docs/SPEC.md` for the full rationale.

Status semantics:

| `status`    | When |
|-------------|------|
| `ok`        | Every required provider succeeded; no per-field fallback fired. |
| `partial`   | One or more providers degraded (anti-bot, missing key, timeout). `data` is still schema-conformant; `error.code` names the cause and `error.suggestion` names the fix. |
| `degraded`  | No provider succeeded. `error.code` names the primary failure and `error.suggestion` gives the next action. |

`error` is required when `status != "ok"` and absent when `status == "ok"`.

## `EnvelopeError`

```python
class EnvelopeError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "ssrf_rejected",
        "network_timeout",
        "blocked_by_antibot",
        "fixture_path_traversal_rejected",
        "response_too_large",
        "no_provider_succeeded",
        "misconfigured_provider",
        "empty_response",
        "cache_corrupted",
    ]
    message: str                     # human-readable — logs / UI
    suggestion: str | None = None    # actionable next step
```

Agents should branch on `error.code`; humans read `error.message`.
`suggestion` is *actionable*: `"configure a smart-proxy provider key"`,
`"skip this prospect"`. Any closed-set change — adding, renaming, or
removing a code — bumps `schema_version`. In the pre-1.0 (0.x) series
all three land as a MINOR bump; rename and removal are called out as
BREAKING in the CHANGELOG so downstream consumers see the break
explicitly. A mapping-only change that makes the same input land on a
different `error.code` is also a MINOR bump. Post-1.0, renames and
removals will require a MAJOR bump.

### Example — `ok`

Zero-key Attempt 1 (`site_text_trafilatura`) populates `pages`; the other
slots are reserved for providers that register later (see
`docs/SPEC.md` — shipped-vs-deferred).

Keys are shown in the alphabetical order the CLI emits
(`json.dumps(..., sort_keys=True)`) so the block is copy-paste reproducible.

```json
{
  "data": {
    "fetched_at": "2026-04-22T18:35:02.767112Z",
    "mentions": null,
    "pages": {
      "about_text": "Acme Bakery has served Portland, OR since 2010. ...",
      "homepage_text": "Acme Bakery is a bakery in Portland, OR. ...",
      "services": ["Custom cakes", "Catering", "Wholesale bread", "Pastry boxes"],
      "tech_stack": ["WordPress", "Elementor"]
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

### Example — `partial` (zero-key blocked, smart-proxy unset)

```json
{
  "data": {
    "fetched_at": "2026-04-22T18:35:14.928144Z",
    "mentions": null,
    "pages": null,
    "reviews": null,
    "signals": null,
    "site": "walled-garden.example",
    "social": null
  },
  "error": {
    "code": "blocked_by_antibot",
    "message": "blocked_by_antibot (HTTP 403)",
    "suggestion": "configure a smart-proxy provider key or skip this prospect"
  },
  "provenance": {
    "site_text_trafilatura": {
      "cost_incurred": 0,
      "error": "blocked_by_antibot (HTTP 403)",
      "latency_ms": 842,
      "provider_version": "0.1.0",
      "status": "failed"
    },
    "smart_proxy_http": {
      "cost_incurred": 0,
      "error": "missing env var: COMPANYCTX_SMART_PROXY_URL — export COMPANYCTX_SMART_PROXY_URL='http://user:pass@host:port' to wire your residential-proxy vendor",
      "latency_ms": 0,
      "provider_version": "0.1.0",
      "status": "not_configured"
    }
  },
  "schema_version": "0.4.0",
  "status": "partial"
}
```

## `CompanyContext`

```python
class CompanyContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Required — always present, even on partial runs.
    site: str                     # e.g. "acme-bakery.com" or "https://acme-bakery.com"
    fetched_at: datetime          # UTC

    # Optional — nullable / empty-collection on partial runs.
    pages: SiteSignals | None = None
    reviews: ReviewsSignals | None = None
    social: SocialSignals | None = None
    mentions: MentionsSignals | None = None
    signals: HeuristicSignals | None = None
```

Nothing else goes at the top level. People-data fields (contact,
decision-maker, enrichment) are out of scope — that enrichment belongs
upstream (Apollo / Clearbit / manual research).

In v0.2, only `pages` populates on a live zero-key or smart-proxy run.
`reviews` / `social` / `signals` / `mentions` stay `null` until their
providers register (see `docs/SPEC.md` for the deferred-provider table
and tracking issues).

## Sub-models

### `SiteSignals`

```python
class SiteSignals(BaseModel):
    homepage_text: str                # cleaned, extractor-agnostic
    about_text: str | None = None
    services: list[str] = []
    tech_stack: list[str] = []        # detected, not claimed
```

### `ReviewsSignals`

```python
class ReviewsSignals(BaseModel):
    count: int
    rating: float | None = None
    source: str                       # provider slug, e.g. "reviews_google_places"
```

### `SocialSignals`

```python
class SocialSignals(BaseModel):
    handles: dict[str, str] = {}           # platform → handle
    follower_counts: dict[str, int] = {}   # platform → count (nullable in v0.1)
```

### `MediaMention`

```python
class MediaMention(BaseModel):
    title: str
    url: str
    source: str                       # publication / podcast / award name
    kind: Literal["press", "podcast", "award", "mention"]
    date: datetime | None = None
```

### `HeuristicSignals`

```python
class HeuristicSignals(BaseModel):
    """Raw observations only — the collector never computes a judgment."""

    team_size_claim: str | None = None        # regex-captured, e.g. "team of 6"
    linkedin_employee_count: int | None = None   # company page only, no people
    hiring_page_active: bool | None = None
    last_funding_round: FundingRound | None = None
    copyright_year: int | None = None
    last_blog_post_at: datetime | None = None
    tech_vs_claim_mismatches: list[str] = []
```

### `MentionsSignals`

```python
class MentionsSignals(BaseModel):
    items: list[MediaMention] = []
```

### `ProviderRunMetadata`

```python
class ProviderRunMetadata(BaseModel):
    status: Literal["ok", "degraded", "failed", "not_configured"]
    latency_ms: int
    error: str | None = None
    provider_version: str
    cost_incurred: int = 0
```

## Invariants

- **Raw observations, not inference.** `CrossReferenceSignals` captures what
  was present on the page; it never computes "small team but high headcount
  claim — possible inflation." Inference is the downstream synthesis
  model's job.
- **Missing is not broken.** Every optional field is nullable. A provider
  that can't fill its slot sets `provenance[slug].status: "degraded"` or
  `"not_configured"`; the field stays null.
- **`extra="forbid"`.** Unknown fields raise on construct — keeps drift
  loud.
- **Versioned.** The top-level `schema_version` field lives alongside
  `__version__`; bumps follow SemVer. Adding an optional field is a PATCH;
  adding a required field, renaming a field, or changing an existing field's
  shape is a MINOR (pre-1.0) / MAJOR (post-1.0). The v0.1→v0.2 `error`-shape
  change is the archetypal minor-release bump.

## Validation

- `companyctx validate <path/to/file.json>` round-trips a payload through
  the Pydantic model and returns exit code 0 on success.
- The two-phase acceptance protocol (blind-eval → 2-week A/B) for integrating
  `companyctx` into a production pipeline lives in `docs/VALIDATION.md`.

## Further reading

- `docs/SPEC.md` — full frozen v0.1 spec.
- `docs/ARCHITECTURE.md` — how the envelope gets populated by the
  Deterministic Waterfall.
- `docs/PROVIDERS.md` — which provider fills which part of the schema.

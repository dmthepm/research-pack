# Zero-Key Mode

`companyctx <site>` returning a schema-locked JSON payload with **no API
keys, no configuration, no rented infrastructure** is the first thing the
README shows. It's the adoption wedge.

This doc is the honest scoping. Zero-key mode does not magically defeat the
internet's anti-bot layer — and pretending otherwise would poison first-run
trust faster than an install bug.

## What zero-key covers

**The stealth fetcher.** `curl_cffi` pinned to `impersonate="chrome146"` —
Python bindings over libcurl-impersonate, MIT-licensed. It mimics a current
Chrome's TLS ClientHello (JA3/JA4), HTTP/2 SETTINGS frame, and header order,
clearing the passive fingerprint check most basic anti-bot layers start
with. The pick is documented in
[`decisions/2026-04-20-zero-key-stealth-strategy.md`](../decisions/2026-04-20-zero-key-stealth-strategy.md)
and the measurement is in
[`research/2026-04-21-tls-impersonation-spike.md`](../research/2026-04-21-tls-impersonation-spike.md).

Backing that, the day-one zero-key providers:

| Provider slug             | What it extracts                       |
|---------------------------|----------------------------------------|
| `site_text_trafilatura`   | Cleaned body text (primary extractor)  |
| `site_text_readability`   | Cleaned body text (bus-factor fallback)|
| `site_meta_extruct`       | JSON-LD / OG / Twitter cards / `sameAs`|
| `social_discovery_site`   | Platform handles via HTML + `sameAs`   |
| `signals_site_heuristic`  | Copyright year, last blog post date, team-size claim, tech-stack fingerprint |

No key required for any of these. They are the `pipx install companyctx &&
companyctx fetch acme-bakery.com` experience.

## The honest coverage matrix

| Site class | Zero-key measured outcome |
|---|---|
| **Small-biz WordPress / Squarespace / Wix / Webflow / small-agency custom** | Full payload on the homepage. The TLS-impersonation fetcher clears the passive checks, and most small-biz stacks don't run aggressive anti-bot. The M1 spike measured **20/20 `status: "ok"`** on a 20-site probe across eight ICP niches (bariatric, biz-immigration, cosmetic-dentistry, fertility, HNW-divorce, real-estate-lending, orthopedics, plastic-surgery) at the latest native Chrome fingerprint; a follow-on shape-balanced probe ([research/2026-04-22](../research/2026-04-22-wix-webflow-spa-probe.md)) confirmed HTTP 200 on every reachable Wix and Webflow endpoint in a 15-site Wix/Webflow/SPA draw.\* |
| **Sites behind Cloudflare Turnstile, DataDome, Akamai, or PerimeterX** | Often blocked on zero-key when the pinned fingerprint is stale. Returns `status: "partial"` with `error.code == "blocked_by_antibot"` and `error.suggestion == "configure a smart-proxy provider key or skip this prospect"`. The payload contains whatever *did* succeed (e.g. `extruct` on a cached preview) — not a crash. |
| **JS-heavy SPAs that need a real browser** | Zero-key fetcher returns the HTML shell only. Schema fields that need rendered content (often `pages.about_text`, some JSON-LD) come back null. `status: "partial"`; configure a smart-proxy + headless-browser provider to fill the gap. The decay mode is *client-only-rendered app shells* (e.g. sign-in-gated dashboards like `manage.wix.com`, which trips the 5-hop redirect cap on anonymous traffic and surfaces as a `partial` envelope), not SSR-rendered SPA **marketing** pages — the 2026-04-22 probe saw 7/7 Next.js / React-rendered SPA marketing homepages clear the 1 KB extract threshold. |
| **Aggregator pages (Yelp / Houzz / G2 / Birdeye)** | Zero-key will not get these — ToS + anti-bot posture make them a bad target. The right path is the `reviews_google_places` / `reviews_yelp_fusion` **direct-API** providers (user-keyed) under Attempt 3 of the Deterministic Waterfall. README must not imply otherwise. |

\* Measurement method, raw per-request JSONL, and hostile-cluster analysis
are in
[`research/2026-04-21-tls-impersonation-spike.md`](../research/2026-04-21-tls-impersonation-spike.md)
(slug-only; the URL→slug mapping is gitignored per the sanitization
contract). **Decay mode.** The real failure mode is fingerprint freshness,
not library identity. A 6-month-stale `chrome131` pin flipped three
Cloudflare-fronted slugs from 200→403 in the same probe run. Mitigation:
we bump the `impersonate=` target with each `curl_cffi` release, and the
`SmartProxyProvider` interface stays the long-term escape hatch when
fingerprint impersonation eventually hits a ceiling. The full 30-prospect
fixtures measurement remains deliberate future work.

## The graceful-partial contract

When zero-key can't fully succeed, `companyctx` does not crash, does not
`sys.exit(1)`, does not raise. It emits the partial envelope:

```json
{
  "schema_version": "0.5.0",
  "status": "partial",
  "data": {
    "site": "example.com",
    "fetched_at": "2026-04-20T18:42:11Z",
    "pages": null,
    "reviews": null,
    "social": { "handles": {"instagram": "@example"}, "follower_counts": {} },
    "signals": null
  },
  "provenance": {
    "site_text_trafilatura": {
      "status": "failed",
      "latency_ms": 2100,
      "error": "blocked_by_antibot (HTTP 403)",
      "provider_version": "0.1.0"
    },
    "site_meta_extruct": {
      "status": "ok",
      "latency_ms": 180,
      "error": null,
      "provider_version": "0.1.0"
    }
  },
  "error": {
    "code": "blocked_by_antibot",
    "message": "blocked_by_antibot (HTTP 403)",
    "suggestion": "configure a smart-proxy provider key or skip this prospect"
  }
}
```

Downstream pipelines branch on `status`:

```python
ctx = fetch_companyctx(site)
if ctx["status"] == "ok":
    synthesize(ctx["data"])
elif ctx["status"] == "partial":
    err = ctx["error"]          # {code, message, suggestion?}
    log.warning("partial: %s — %s", err["code"], err.get("suggestion"))
    synthesize_with_caveat(ctx["data"])   # pipeline-safe, not a skip
else:  # degraded (nothing usable succeeded)
    synthesize(ctx["data"])               # or route to a fallback/skip path
```

No try/except around a crash. No `None` return values bubbling through
nothing. The envelope is always well-formed.

## What to do when zero-key isn't enough

**Option A — configure a smart-proxy provider.** `companyctx` ships a
vendor-agnostic URL-style implementation (`smart_proxy_http`). Set
`COMPANYCTX_SMART_PROXY_URL=http://user:pass@host:port` to the full URL
your residential-proxy vendor gave you — anti-bot-blocked fetches route
through it as Attempt 2, and the envelope's top-level status flips from
`partial` to `ok` for that prospect. If your vendor requires a custom CA,
set `COMPANYCTX_SMART_PROXY_VERIFY=/path/to/ca.pem` as well.

> **Pending measurement.** A **named reference adapter** over a specific
> vendor — shipped as an optional extra — lands after the smart-proxy
> vendor eval spike. No vendor is named in these docs until that
> measurement is in.

**Option B — configure direct-API providers.** For review counts / ratings /
social follower counts, the right path is the platform's own API, not
scraping. Google Places (`GOOGLE_PLACES_API_KEY`), Yelp Fusion
(`YELP_API_KEY`), YouTube Data API (`YOUTUBE_API_KEY`). Each is env-gated;
if the key isn't set, the provider reports
`provenance[slug].status: "not_configured"` and the envelope still comes back
well-formed.

**Option C — skip this prospect.** If zero-key returns partial and you
don't want to pay for smart-proxy access, the envelope's
`suggestion: "skip this prospect"` is a valid pipeline decision. Log it,
move on, don't bend the tool.

## What zero-key is *not*

- **Not a promise of 100% coverage.** See the matrix above.
- **Not a Cloudflare bypass tool.** If the site is serious about blocking
  bots, we report the block and route to user-keyed providers. We don't
  out-engineer Cloudflare.
- **Not a scraper for ToS-protected aggregators.** Yelp / Houzz / G2 don't
  get scraped via zero-key; they get queried via direct-API providers.
- **Not a guarantee of field completeness on small-biz sites either.**
  Some homepages just don't have a team-size claim, a copyright footer,
  or recent blog posts — those stay null without it being a failure.

## M1 spike — completed

The TLS-impersonation library spike ran on 2026-04-21 against a 20-site
probe drawn from eight ICP niches. Outcome:

- Library pick: **`curl_cffi` at `impersonate="chrome146"`**.
- At the latest native Chrome fingerprint: **20/20** `status: "ok"`.
- At a 6-month-stale `chrome131` fingerprint: 3 slugs flipped to
  `blocked_by_antibot (HTTP 403)` — the fingerprint-freshness decay
  signal.
- `rnet` was disqualified by GPL-3.0 license; `primp` lost on silent
  fallback to a random fingerprint when an impersonation name was
  misspelled (a determinism hazard). See the research doc for the
  full matrix.

Full method, raw JSONL evidence, and rationale:
[`research/2026-04-21-tls-impersonation-spike.md`](../research/2026-04-21-tls-impersonation-spike.md).
ADR promotion:
[`decisions/2026-04-20-zero-key-stealth-strategy.md`](../decisions/2026-04-20-zero-key-stealth-strategy.md)
is now `status: accepted`.

The 30-prospect fixtures corpus measurement remains future work; the
20-site spike is the number the README hero cites today.

#!/usr/bin/env bash
# 01-basic-fetch.sh — the hello-world recipe.
#
# Fetches one domain, pretty-prints the JSON envelope. Nothing else.
# This is the shape every other recipe in the gallery builds on.
#
# Uses --mock to stay self-contained: runs against the fixture corpus
# shipped in the repo, so no network, no keys, byte-identical output
# modulo fetched_at.
#
# Usage:
#   ./01-basic-fetch.sh
#   ./01-basic-fetch.sh acme-bakery          # any fixture slug
#   ./01-basic-fetch.sh acme-bakery.com --live   # real fetch, zero-key path

set -euo pipefail

SITE="${1:-acme-bakery}"
MODE="${2:---mock}"

if [ "$MODE" = "--live" ]; then
  companyctx fetch "$SITE" --json
else
  companyctx fetch "$SITE" --mock --json
fi

# --- EXPECTED OUTPUT (current envelope, keys sorted by the CLI) ---
# {
#   "data": {
#     "fetched_at": "2026-04-22T18:44:05.810816Z",
#     "mentions": null,
#     "pages": {
#       "about_text": "Acme Bakery has served Portland, OR since 2010. ...",
#       "homepage_text": "Acme Bakery is a bakery in Portland, OR. ...",
#       "services": ["Custom cakes", "Catering", "Wholesale bread", "Pastry boxes"],
#       "tech_stack": ["WordPress", "Elementor"]
#     },
#     "reviews": null,
#     "signals": null,
#     "site": "acme-bakery",
#     "social": null
#   },
#   "error": null,
#   "provenance": {
#     "site_text_trafilatura": {
#       "cost_incurred": 0,
#       "error": null,
#       "latency_ms": 0,
#       "provider_version": "0.1.0",
#       "status": "ok"
#     }
#   },
#   "schema_version": "0.5.0",
#   "status": "ok"
# }
#
# Note: the default mock path exercises the zero-key baseline, so
# `data.reviews` / `data.social` / `data.signals` / `data.mentions`
# still read null here. Those slots remain schema-stable and fill as
# their providers are configured or shipped — see docs/SPEC.md.

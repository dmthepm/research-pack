#!/usr/bin/env bash
# 02-jq-filtering.sh — the UNIX pipe pattern.
#
# Shows how to pipe the envelope through `jq` to extract just the
# fields you care about. This is the single most common shape —
# every downstream recipe in the gallery composes on top of it.
#
# The key idea: `companyctx` emits one predictable JSON object;
# `jq` reshapes it into whatever your next step needs. No parsing,
# no regex, no brittle HTML scraping.
#
# Requires: jq (brew install jq / apt install jq)
# Usage:    ./02-jq-filtering.sh

set -euo pipefail

SITE="${1:-acme-bakery}"

echo "=== Just the services and tech stack ==="
companyctx fetch "$SITE" --mock --json \
  | jq '.data | { site, services: .pages.services, stack: .pages.tech_stack }'

echo
echo "=== Social handles as a flat list ==="
companyctx fetch "$SITE" --mock --json \
  | jq -r '(.data.social.handles // {}) | to_entries[] | "\(.key): \(.value)"'

echo
echo "=== Review summary, or a fallback string if unavailable ==="
companyctx fetch "$SITE" --mock --json \
  | jq -r '
      if .data.reviews then
        "\(.data.reviews.rating)★ across \(.data.reviews.count) reviews (\(.data.reviews.source))"
      else
        "no review data for this provider set"
      end
    '

echo
echo "=== Branch on status — the pipeline contract ==="
STATUS=$(companyctx fetch "$SITE" --mock --json | jq -r '.status')
case "$STATUS" in
  ok)       echo "✅ complete envelope — safe to synthesize" ;;
  partial)  echo "⚠️  some providers failed — check .provenance for which" ;;
  degraded) echo "❌ primary fetch blocked — see .error.code / .error.suggestion" ;;
esac

# --- EXPECTED OUTPUT (current mock baseline — pages populated, other slots null) ---
# === Just the services and tech stack ===
# {
#   "site": "acme-bakery",
#   "services": ["Custom cakes", "Catering", "Wholesale bread", "Pastry boxes"],
#   "stack": ["WordPress", "Elementor"]
# }
#
# === Social handles as a flat list ===
# (empty — data.social is still null on the current mock baseline)
#
# === Review summary, or a fallback string if unavailable ===
# no review data for this provider set
#
# === Branch on status — the pipeline contract ===
# ✅ complete envelope — safe to synthesize
#
# Note: the review / social branches above are the exact fallbacks your
# pipeline should rely on — they kick in whenever a slot's provider
# isn't configured or hasn't landed yet. The jq pipe does not change as
# more providers start populating fields.

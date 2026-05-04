#!/usr/bin/env bash
# 04-sales-meeting-prep.sh — 5-second discovery-call cheat sheet.
#
# A sales rep has a Zoom call in 60 seconds with a prospect they know
# nothing about. Instead of frantically clicking through the website,
# they run this script and get a structured cheat sheet printed right
# in their terminal.
#
# Business value: turns a cold discovery call into a warm one without
# any CRM upgrade or subscription — the rep just needs the CLI and
# the domain name.
#
# Requires: jq
# Usage:    ./04-sales-meeting-prep.sh acme-bakery
#           ./04-sales-meeting-prep.sh acme-bakery.com --live

set -euo pipefail

SITE="${1:-acme-bakery}"
MODE="${2:---mock}"

FETCH_FLAGS="--mock --json"
if [ "$MODE" = "--live" ]; then
  FETCH_FLAGS="--json"
fi

echo "======================================================"
echo "  SALES CHEAT SHEET — $SITE"
echo "======================================================"

# Fetch once, reuse.
# shellcheck disable=SC2086
DATA=$(companyctx fetch "$SITE" $FETCH_FLAGS)

STATUS=$(echo "$DATA" | jq -r '.status')
if [ "$STATUS" != "ok" ]; then
  CODE=$(echo "$DATA" | jq -r '.error.code // "unknown"')
  MSG=$(echo "$DATA" | jq -r '.error.message // "unknown"')
  SUGGESTION=$(echo "$DATA" | jq -r '.error.suggestion // "none"')
  echo "⚠️  Envelope status: $STATUS"
  echo "   code:       $CODE"
  echo "   message:    $MSG"
  echo "   suggestion: $SUGGESTION"
  echo "   — proceed with the partial info below —"
  echo
fi

SERVICES=$(echo "$DATA" | jq -r '.data.pages.services // [] | join(", ")')
TECH=$(echo "$DATA" | jq -r '.data.pages.tech_stack // [] | join(", ")')
RATING=$(echo "$DATA" | jq -r '.data.reviews.rating // "n/a"')
REVIEWS=$(echo "$DATA" | jq -r '.data.reviews.count // 0')
REV_SOURCE=$(echo "$DATA" | jq -r '.data.reviews.source // "—"')
TEAM=$(echo "$DATA" | jq -r '.data.signals.team_size_claim // "not stated"')
COPYRIGHT=$(echo "$DATA" | jq -r '.data.signals.copyright_year // "not stated"')
LAST_POST=$(echo "$DATA" | jq -r '.data.signals.last_blog_post_at // "not stated"')
SOCIAL=$(echo "$DATA" | jq -r '.data.social.handles // {} | to_entries[] | "    \(.key): \(.value)"')

echo "🏢 WHAT THEY DO"
echo "    $SERVICES"
echo
echo "💻 HOW THEY OPERATE"
echo "    tech stack: $TECH"
echo
echo "👥 TEAM + CADENCE"
echo "    team:           $TEAM"
echo "    copyright:      $COPYRIGHT"
echo "    last blog post: $LAST_POST"
echo
echo "⭐ MARKET REPUTATION"
if [ "$RATING" = "n/a" ]; then
  echo "    no review data available"
else
  echo "    $RATING★ across $REVIEWS reviews (source: $REV_SOURCE)"
fi
echo
if [ -n "$SOCIAL" ]; then
  echo "🔗 SOCIAL"
  echo "$SOCIAL"
  echo
fi
echo "======================================================"
echo "💡 Rep tip: mention one specific item above in the first"
echo "   90 seconds of the call to prove you did your homework."
echo "======================================================"

# --- EXPECTED OUTPUT (current mock baseline — pages populated, other slots null) ---
# ======================================================
#   SALES CHEAT SHEET — acme-bakery
# ======================================================
# 🏢 WHAT THEY DO
#     Custom cakes, Catering, Wholesale bread, Pastry boxes
#
# 💻 HOW THEY OPERATE
#     tech stack: WordPress, Elementor
#
# 👥 TEAM + CADENCE
#     team:           not stated
#     copyright:      not stated
#     last blog post: not stated
#
# ⭐ MARKET REPUTATION
#     no review data available
#
# ======================================================
# 💡 Rep tip: mention one specific item above in the first
#    90 seconds of the call to prove you did your homework.
# ======================================================
#
# Note: "not stated" and "no review data available" reflect the current
# mock baseline — data.signals / data.reviews / data.social are still
# null there. The jq fallbacks in this script (// "not stated", //
# "n/a") are the exact shape a production pipeline should use; they
# start filling in as providers are configured or shipped.

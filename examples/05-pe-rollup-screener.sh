#!/usr/bin/env bash
# 05-pe-rollup-screener.sh — M&A screener for sleepy-but-loved SMBs.
#
# The micro-PE / search-fund / M&A thesis: the most interesting
# rollup targets are businesses with strong local reputation but
# weak tech and marketing. Manually screening them does not scale.
#
# This script runs a deterministic filter across a list of domains:
#
#     reviews.rating      >= 4.5        (customers love them)
#     reviews.count       >= 75         (the love is statistically real)
#     pages.tech_stack    has WordPress (dated-enough stack that a
#                                        software-forward acquirer
#                                        can unlock value)
#     signals.copyright   <= 2023       (website hasn't been touched
#                                        recently — a tell)
#
# Tune the thresholds for your thesis; the shape is what matters.
#
# NOTE: this thesis reads `data.reviews` and `data.signals`. On the
# current mock baseline those slots are still null, so the screener
# returns 0 candidates. The shape is deliberately preserved — once a
# review provider is configured (export `GOOGLE_PLACES_API_KEY` and
# drop `--mock`), the same filter starts producing hits without any
# change to this script.
#
# Requires: jq
# Usage:    ./05-pe-rollup-screener.sh          # uses embedded demo list
#           ./05-pe-rollup-screener.sh my-list.txt

set -euo pipefail

# Self-contained: if no file is passed, heredoc the demo list.
# This keeps the recipe instantly runnable by anyone who clones
# the repo — no "please create targets.txt" friction.
TARGETS_FILE="${1:-}"
if [ -z "$TARGETS_FILE" ]; then
  TARGETS_FILE="$(mktemp)"
  cat > "$TARGETS_FILE" <<'EOF'
acme-bakery
brightsmile-dental
cornerstone-bakery
forge-fitness
hilltop-contractor
ironworks-contractor
keystone-contractor
oakleaf-bakery
pinewood-agency
redwood-contractor
EOF
  CLEANUP_TARGETS=1
else
  CLEANUP_TARGETS=0
fi

echo "🔍 Screening for rollup candidates"
echo "   thesis: rating ≥ 4.5, ≥ 75 reviews, WordPress, copyright ≤ 2023"
echo "--------------------------------------------------------------------"

HITS=0
while IFS= read -r domain; do
  [ -z "$domain" ] && continue

  # Use --mock for self-contained demo runs. Swap to live for real screening.
  HIT=$(companyctx fetch "$domain" --mock --json \
    | jq -r '
        select(
          .status == "ok"
          and .data.reviews != null
          and .data.reviews.rating >= 4.5
          and .data.reviews.count  >= 75
          and (.data.pages.tech_stack // [] | index("WordPress"))
          and (.data.signals.copyright_year // 9999) <= 2023
        )
        | "✅ \(.data.site) | \(.data.reviews.rating)★ × \(.data.reviews.count) reviews | stack: \(.data.pages.tech_stack | join(",")) | copyright \(.data.signals.copyright_year)"
      ')

  if [ -n "$HIT" ]; then
    echo "$HIT"
    HITS=$((HITS + 1))
  fi
done < "$TARGETS_FILE"

[ "$CLEANUP_TARGETS" = "1" ] && rm -f "$TARGETS_FILE"

echo "--------------------------------------------------------------------"
echo "Done. $HITS candidate(s) matched the thesis."
echo "Next: hand the hits to a human analyst for diligence, or pipe into"
echo "      a brief-generation step (see 03-brains-and-muscles.sh)."

# --- EXPECTED OUTPUT (current mock baseline) ---
# 🔍 Screening for rollup candidates
#    thesis: rating ≥ 4.5, ≥ 75 reviews, WordPress, copyright ≤ 2023
# --------------------------------------------------------------------
# --------------------------------------------------------------------
# Done. 0 candidate(s) matched the thesis.
# Next: hand the hits to a human analyst for diligence, or pipe into
#       a brief-generation step (see 03-brains-and-muscles.sh).
#
# Reason: the thesis filters on data.reviews.* and data.signals.*,
# which are null on the current mock baseline (see header note). Once a
# review provider is configured the filter starts producing hits:
#
# ✅ acme-bakery         | 4.6★ × 142 reviews | stack: WordPress,Elementor | copyright 2023
# ✅ cornerstone-bakery  | 4.7★ ×  96 reviews | stack: WordPress,WooCommerce | copyright 2022
# ✅ hilltop-contractor  | 4.8★ × 210 reviews | stack: WordPress            | copyright 2021

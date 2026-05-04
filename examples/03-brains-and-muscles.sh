#!/usr/bin/env bash
# 03-brains-and-muscles.sh — the canonical 2026 agentic pipe.
#
# The whole companyctx design philosophy in one command:
#
#     muscle  →  pipe  →  brain
#
# muscle: `companyctx` fetches the deterministic JSON envelope.
# pipe:   stdin / stdout, the UNIX contract.
# brain:  Simon Willison's `llm` CLI synthesizes against a prompt.
#
# No LangChain, no agent framework, no orchestrator — just one
# primitive that extracts and one primitive that reasons. The
# envelope is the contract between them.
#
# Requires: pipx install llm && llm keys set anthropic  (or openai)
# Usage:    ./03-brains-and-muscles.sh acme-bakery
#           ./03-brains-and-muscles.sh acme-bakery --live   # live fetch

set -euo pipefail

SITE="${1:-acme-bakery}"
MODE="${2:---mock}"

FETCH_FLAGS="--mock --json"
if [ "$MODE" = "--live" ]; then
  FETCH_FLAGS="--json"
fi

# The magic one-liner: the envelope is the prompt context.
# shellcheck disable=SC2086
companyctx fetch "$SITE" $FETCH_FLAGS \
  | llm -s "
You are an elite outbound SDR. You're receiving a deterministic JSON
payload containing the technical and business context of a target
company. The payload is your only source of truth about the prospect.

Read the JSON. Pay special attention to:
  - data.pages.services       (what they sell)
  - data.pages.tech_stack     (how they operate)
  - data.pages.homepage_text  (their positioning)
  - data.reviews              (market reputation — null unless a review
                               provider is configured)
  - data.signals              (copyright year, team size, cadence — null
                               until the site-heuristic provider ships)

Write a 3-sentence cold email pitching our generic AI-automation
services. Reference exactly one specific piece of their tech stack or
one specific service they offer to prove you did your research. Do
not invent facts that aren't in the payload (including: if a field is
null, treat it as unknown, not as 'no reviews'). Output only the email
body — no subject line, no sign-off.
"

# --- EXPECTED OUTPUT (illustrative — the LLM will vary) ---
# Hi team,
#
# I noticed Acme Bakery is running its custom-cakes ordering on
# WordPress + Elementor — we help small-batch bakeries like yours
# shave hours off weekly order intake by dropping a zero-code
# intake flow on top of that exact stack. A quick 15-minute look
# could show you whether it's worth pursuing — open to a call
# Thursday?

"""08-support-ticket-context.py — inject customer context into a support agent.

When a B2B customer submits a support ticket, a generic support bot
(or a human agent reading it cold) wastes cycles asking "what
platform are you on?" and "what do you sell?" This recipe infers the
customer's domain from their email, enriches it with ``companyctx``,
and produces a structured internal note the support system can
attach to the ticket.

The output is two things:

1. A human-readable internal note — drop it into Zendesk / Intercom /
   Freshdesk / Help Scout as an internal comment.
2. A structured ``context_block`` dict — inject it into an AI
   support agent's system prompt so the agent answers with
   business-aware specificity instead of boilerplate.

Usage:
    python 08-support-ticket-context.py                       # uses demo ticket + --mock
    python 08-support-ticket-context.py --email <e> --msg <m>

The recipe is dependency-free beyond ``companyctx``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from companyctx.core import run


def generate_support_context(
    customer_email: str,
    ticket_message: str,
    *,
    mock: bool = False,
) -> dict[str, Any]:
    """Return both a human note and a machine-readable context block."""
    if "@" not in customer_email:
        return {
            "note": "AUTOMATED CONTEXT: skipped — malformed customer email.",
            "context_block": None,
        }

    domain = customer_email.split("@", 1)[1]
    # Resolve fixtures/ relative to this script so the recipe runs from
    # anywhere (including `cd examples && python 08-...`).
    fixtures_dir = (Path(__file__).resolve().parent.parent / "fixtures") if mock else None
    envelope = run(domain, mock=mock, fixtures_dir=fixtures_dir)

    if envelope.status != "ok":
        detail = (
            f"{envelope.error.code}: {envelope.error.message}"
            if envelope.error is not None
            else "no error detail"
        )
        return {
            "note": (
                "AUTOMATED CONTEXT: could not enrich customer — "
                f"envelope status {envelope.status} ({detail})."
            ),
            "context_block": None,
        }

    data = envelope.data
    services = (data.pages.services if data.pages else []) or ["unknown"]
    tech = (data.pages.tech_stack if data.pages else []) or ["unknown"]
    team = data.signals.team_size_claim if data.signals else None
    handles = dict(data.social.handles) if data.social else {}

    note_lines = [
        "--- AUTOMATED CUSTOMER CONTEXT ---",
        f"Domain:           {domain}",
        f"What they sell:   {', '.join(services)}",
        f"Their tech stack: {', '.join(tech)}",
    ]
    if team:
        note_lines.append(f"Team size claim:  {team}")
    if handles:
        handles_str = ", ".join(f"{k}: {v}" for k, v in sorted(handles.items()))
        note_lines.append(f"Social:           {handles_str}")
    note_lines.append(f"Ticket excerpt:   {ticket_message[:120]}")
    note_lines.append(
        "Suggested action: tailor the reply to their tech stack; avoid generic boilerplate."
    )
    note_lines.append("----------------------------------")

    context_block: dict[str, Any] = {
        "customer_domain": domain,
        "customer_services": list(services),
        "customer_tech_stack": list(tech),
        "customer_team_size_claim": team,
        "customer_social_handles": handles,
    }

    return {"note": "\n".join(note_lines), "context_block": context_block}


def _demo_ticket() -> tuple[str, str]:
    return (
        "ops@acme-bakery",
        "Our online orders stopped syncing to the kitchen printer yesterday. Can you help?",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", help="Customer email. Defaults to demo ticket.")
    parser.add_argument("--msg", help="Ticket message. Defaults to demo ticket.")
    parser.add_argument("--mock", action="store_true", help="Use fixtures corpus.")
    args = parser.parse_args()

    if args.email and args.msg:
        email, message = args.email, args.msg
    else:
        email, message = _demo_ticket()

    result = generate_support_context(email, message, mock=args.mock or not args.email)

    print("### Internal note (paste into Zendesk / Intercom / Freshdesk):")
    print(result["note"])
    print()
    print("### Machine context block (inject into your agent's system prompt):")
    print(json.dumps(result["context_block"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()


# --- EXPECTED OUTPUT (current mock baseline, demo ticket) ---
# ### Internal note (paste into Zendesk / Intercom / Freshdesk):
# --- AUTOMATED CUSTOMER CONTEXT ---
# Domain:           acme-bakery
# What they sell:   Custom cakes, Catering, Wholesale bread, Pastry boxes
# Their tech stack: WordPress, Elementor
# Ticket excerpt:   Our online orders stopped syncing to the kitchen printer yesterday. ...
# Suggested action: tailor the reply to their tech stack; avoid generic boilerplate.
# ----------------------------------
#
# ### Machine context block (inject into your agent's system prompt):
# {
#   "customer_domain": "acme-bakery",
#   "customer_services": ["Custom cakes", "Catering", "Wholesale bread", "Pastry boxes"],
#   "customer_social_handles": {},
#   "customer_team_size_claim": null,
#   "customer_tech_stack": ["WordPress", "Elementor"]
# }
#
# Note: "Team size claim" / "Social:" don't appear in the note when
# data.signals / data.social are null on the current mock baseline.
# Once those providers land, the lines appear automatically — no
# script change.

"""Inbound-lead webhook enrichment handler.

Drop ``handle_inbound_lead`` into any runtime you like:

- AWS Lambda: wrap as the ``lambda_handler`` (return ``dict``).
- n8n / Make: paste the function body into a Code node.
- FastAPI / Flask: wire it behind your webhook route.
- CLI / cron: run this file directly — the ``__main__`` block shows the shape.

The handler itself is sync and dependency-free beyond ``companyctx``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from companyctx.core import run

FREE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "icloud.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
    }
)


def handle_inbound_lead(event: dict[str, Any], *, mock: bool = False) -> dict[str, Any]:
    """Enrich an inbound-lead webhook event.

    Returns a dict with either a ``crm_payload`` ready to push, or a
    ``status`` explaining why we skipped (free email, invalid domain,
    or a non-ok envelope with an actionable suggestion).
    """
    email = (event.get("email") or "").strip().lower()
    if "@" not in email:
        return {"status": "ignored", "reason": "missing or malformed email"}

    domain = email.split("@", 1)[1]
    if domain in FREE_EMAIL_DOMAINS:
        return {"status": "ignored", "reason": "free email provider"}

    # Resolve fixtures/ relative to this script so the recipe runs from any
    # CWD (including `cd examples/07-inbound-webhook-enrichment && python
    # main.py`). In real use (no --mock) fixtures_dir stays None.
    fixtures_dir = (Path(__file__).resolve().parent.parent.parent / "fixtures") if mock else None
    envelope = run(domain, mock=mock, fixtures_dir=fixtures_dir)

    if envelope.status != "ok":
        error = envelope.error
        return {
            "status": "degraded",
            "reason_code": error.code if error else "unknown",
            "reason": error.message if error else "envelope not ok",
            "suggestion": error.suggestion if error else None,
            "domain": domain,
        }

    data = envelope.data
    crm_payload: dict[str, Any] = {
        "company_domain": domain,
        "primary_services": data.pages.services if data.pages else [],
        "tech_stack_detected": data.pages.tech_stack if data.pages else [],
        "review_rating": data.reviews.rating if data.reviews else None,
        "review_count": data.reviews.count if data.reviews else None,
        "review_source": data.reviews.source if data.reviews else None,
        "social_handles": dict(data.social.handles) if data.social else {},
        "copyright_year": data.signals.copyright_year if data.signals else None,
        "team_size_claim": data.signals.team_size_claim if data.signals else None,
        "context_fetched_at": data.fetched_at.isoformat(),
    }

    return {
        "status": "enriched",
        "domain": domain,
        "crm_payload": crm_payload,
    }


def _demo_event() -> dict[str, Any]:
    return {"email": "josh@acme-bakery"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Inbound webhook enrichment demo")
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read a JSON webhook event from stdin instead of using the demo event.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use the fixtures corpus instead of a live fetch.",
    )
    args = parser.parse_args()

    event = json.load(sys.stdin) if args.stdin else _demo_event()

    result = handle_inbound_lead(event, mock=args.mock or not args.stdin)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()


# --- EXPECTED OUTPUT (current mock baseline, demo event) ---
# {
#   "crm_payload": {
#     "company_domain": "acme-bakery",
#     "context_fetched_at": "2026-04-22T18:46:29.655450+00:00",
#     "copyright_year": null,
#     "primary_services": ["Custom cakes", "Catering", "Wholesale bread", "Pastry boxes"],
#     "review_count": null,
#     "review_rating": null,
#     "review_source": null,
#     "social_handles": {},
#     "team_size_claim": null,
#     "tech_stack_detected": ["WordPress", "Elementor"]
#   },
#   "domain": "acme-bakery",
#   "status": "enriched"
# }
#
# Note: primary_services + tech_stack_detected come from the shipped
# zero-key provider. `review_*` / `social_handles` / `team_size_claim` /
# `copyright_year` are still null on the current mock baseline. The CRM
# payload's field map is deliberately stable; once those providers are
# configured or shipped, the null fields start filling in without any
# code change.

# 07 · Inbound webhook enrichment

## Problem

An inbound lead submits only an email (`josh@acme-bakery.example.test`) via
a demo-request form. The RevOps team needs the company's services,
tech stack, review footprint, and rough size on the CRM record
*before* the first sales reply. Standing options:

- Pay a legacy enrichment vendor (Clearbit-class, ZoomInfo-class)
  $12k–$30k/year — pricing and data model built for the pre-agent era.
- Manually research the prospect — slow, inconsistent, doesn't scale.

## Solution

A tiny handler that accepts a webhook payload, pulls the domain from
the email, calls `companyctx`, and maps the deterministic envelope
into a CRM-shaped payload. Runs locally, serverlessly, or in whatever
workflow runner you already own (n8n, Make, Lambda, Cloud Run, a
Rails worker — the handler is plain Python, the CRM mapping is the
only part that differs per integration).

**What you save:** the enrichment-vendor line item.
**What you get:** a deterministic, schema-locked JSON envelope you
can version and diff, rather than a vendor's opaque result set.

Today the CRM payload always fills in `primary_services` +
`tech_stack_detected` from the zero-key provider. `review_*`,
`social_handles`, `team_size_claim`, and `copyright_year` may still
arrive null depending on which providers are configured (see
[`../../docs/SPEC.md`](../../docs/SPEC.md)). The payload shape is
stable; nothing downstream changes when those slots start filling in.

## How to run it

```bash
# From this directory:
pip install -r requirements.txt

# Run the handler against the built-in demo event (uses --mock).
python main.py

# Or feed your own webhook event on stdin:
echo '{"email":"josh@acme-bakery"}' | python main.py --stdin --mock
```

## Files

- `main.py` — the handler. Pure function `handle_inbound_lead(event)`
  wrapped in a `__main__` that runs the demo event. Drop
  `handle_inbound_lead` into an AWS Lambda, an n8n code node, or a
  FastAPI endpoint unchanged.
- `requirements.txt` — `companyctx` only. No framework dependencies.

## Notes on CRM mapping

`main.py` emits a generic `crm_payload` dict with field names like
`company_domain` and `primary_services`. Map those to your CRM's
field names in your own integration — HubSpot uses `domain`,
Salesforce uses `Website`, Attio uses `web_url`. The recipe stays
portable; the mapping is the last-mile step.

## Free-email filter

The handler skips free-email domains (`gmail.com`, `yahoo.com`,
`outlook.com`, etc.) because there's nothing business-useful to
enrich there. Extend the set in `main.py` if your ICP needs it.

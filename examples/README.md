# `examples/` — `companyctx` recipes gallery

This folder is a curated, zero-to-hero progression. Each file is a
self-contained recipe that solves a real business problem using
`companyctx`'s schema-locked JSON envelope.

## Prerequisites

Install `companyctx` first — **every recipe in this gallery assumes the
CLI and package are on the Python path**:

```bash
# From a clean checkout, either:
pipx install companyctx            # CLI on PATH; enough for bash recipes
# or, for the .py recipes that `from companyctx.core import run`:
pip install -e ".[dev,extract,reviews,youtube]"
```

Without one of those, the `.sh` scripts fail at the first `companyctx`
invocation and the `.py` scripts fail at import.

## The primitive

Every example assumes the same primitive:

```bash
companyctx fetch <domain> --json
```

…and shows a different downstream shape — `jq` filter, LLM synthesis,
CRM payload, diff-and-alert, agent-prompt injection. The muscle is
always the same; the orchestration around it is what changes.

### What to expect today

Today the default paths populate `data.pages.*`, and `data.reviews`
can populate when `reviews_google_places` is configured. `data.social`,
`data.signals`, and `data.mentions` remain mostly null until their
providers land. Every recipe in this gallery is coded against the
stable envelope shape with fallbacks for missing slots; nothing
downstream needs a rewrite when a new provider starts filling a field.

## How this folder is built

1. **Zero to hero.** Files are numbered. Start at `01`, work up. Each
   step adds one idea on top of the last.
2. **Self-contained.** No hidden `.env` files, no external inputs.
   Where a recipe needs sample data, it heredocs the data into the
   script itself.
3. **Expected output in-line.** Every script ends with an
   `--- EXPECTED OUTPUT ---` comment block so you can see what the
   recipe produces before you run it.
4. **Micro-READMEs for complex recipes.** When an example needs more
   than a single file (webhook harnesses, multi-step pipelines), it
   lives in its own folder with a `README.md` using the
   Problem / Solution / Run-it format.
5. **Designed to be bit-rot-resistant.** The gallery is written so each
   recipe is runnable in isolation. Dedicated examples CI is still
   tracked separately in #60; until that lands, treat the expected-output
   blocks as the review surface.

## The gallery

| File | Use case | Target operator |
|---|---|---|
| [`01-basic-fetch.sh`](01-basic-fetch.sh) | Hello-world fetch + pretty-print | Anyone |
| [`02-jq-filtering.sh`](02-jq-filtering.sh) | Extract specific fields via UNIX pipe | CLI-fluent devs |
| [`03-brains-and-muscles.sh`](03-brains-and-muscles.sh) | Pipe JSON into an LLM to synthesize a cold email | Outbound / growth |
| [`04-sales-meeting-prep.sh`](04-sales-meeting-prep.sh) | Terminal cheat-sheet right before a discovery call | AEs, SDRs |
| [`05-pe-rollup-screener.sh`](05-pe-rollup-screener.sh) | Filter domain lists for acquisition candidates | Micro-PE, search funds, M&A |
| [`06-competitor-monitor.py`](06-competitor-monitor.py) | Daily JSON diff + change alert | Founders, PMMs |
| [`07-inbound-webhook-enrichment/`](07-inbound-webhook-enrichment/) | Webhook → domain → CRM payload | RevOps, growth |
| [`08-support-ticket-context.py`](08-support-ticket-context.py) | Inject customer context into a support-agent prompt | CS, AI-support builders |
| [`../docs/PARTNER-INTEGRATION.md`](../docs/PARTNER-INTEGRATION.md) | Canonical downstream integration contract for replacing the "LLM reads HTML" step | Operators integrating the envelope |

## The four use cases the gallery covers

`companyctx` started life as the deterministic muscle for a partner's
cold-outreach wedge. The same schema-locked envelope plugs into four
adjacent use cases that the gallery demonstrates in code.

### 1. Inbound lead enrichment → `07-inbound-webhook-enrichment/`

- **Target.** RevOps managers and growth marketers running lifecycle
  on inbound B2B leads.
- **Pain.** A lead submits an email. Sales or lifecycle needs the
  company's services, stack, size, and review footprint before the
  first reply, and the standing options are paid legacy enrichment
  vendors whose pricing, latency, and data model were built for the
  pre-agent era.
- **Why it matters.** Deterministic JSON, no per-call billing on the
  zero-key path, and a schema designed to be *input for synthesis* —
  exactly the wedge the incumbents were not built for.

### 2. PE / SMB rollup sourcing → `05-pe-rollup-screener.sh`

- **Target.** Micro-PE firms, search funds, and M&A analysts
  screening local-service businesses for acquisition.
- **Pain.** The most interesting rollup targets are businesses with
  strong local reputation but weak tech and marketing. Manually
  screening them — review counts, copyright years, stale blogs,
  dated stacks — does not scale past a hundred domains.
- **Why it matters.** The same cache that speeds cold-outreach
  doubles as a queryable SMB dataset for deal flow. One filter
  pipeline, hundreds of domains, zero data-broker spend.

### 3. Automated competitor tracking → `06-competitor-monitor.py`

- **Target.** Founders and product marketers tracking a handful of
  competitors.
- **Pain.** Today's options are manual re-reads or bloated enterprise
  tools. Freeform LLM summarization of raw HTML produces false
  positives — the "competitor relaunched" alert that turns out to be
  a CSS rename.
- **Why it matters.** Deterministic JSON with an `extra="forbid"`
  schema means diffs are stable by construction. Fewer false
  positives than HTML scraping; far fewer than "ask the model what
  changed."

### 4. Dynamic agentic customer support → `08-support-ticket-context.py`

- **Target.** Customer success teams and AI-support builders.
- **Pain.** Support agents (human or AI) answer generically when they
  lack business and stack context about the customer on the other end
  of the ticket.
- **Why it matters.** Upgrades a generic bot into something closer
  to a solutions engineer. Matches the brains-and-muscles pattern
  cleanly: the agent is the brain, `companyctx` is the muscle, the
  envelope is the contract between them.

## Guardrails this gallery respects

- **The primitive is not the product.** `companyctx` is the muscle.
  The value end-buyers pay for — prompts, orchestration, playbooks,
  live implementation — is Noontide's Main Branch and the agency
  practice, not this CLI. These examples show the primitive in
  motion; they do not ship opinionated business logic.
- **Raw observations only.** The envelope is what providers measured.
  Inference belongs in whatever synthesis step consumes the JSON —
  the `llm` pipe, the CRM enrichment mapper, the diff-and-alert
  filter. Not here.
- **No vendor names in the recipe logic.** The examples use generic
  verbs (`jq`, `llm`, "your CRM", "your support system"). Vendor-
  specific integrations (HubSpot, Zendesk, n8n, Make, Lambda) live
  in separate docs so the recipes stay portable.
- **Companies only.** Every example reads `data.site`, `data.pages`,
  `data.reviews`, `data.social`, `data.signals`, `data.mentions`.
  No example extracts or infers people data — that belongs in
  dedicated contact-enrichment tools.

## Related

- **Architecture:** [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)
- **Schema:** [`../docs/SCHEMA.md`](../docs/SCHEMA.md)
- **Provider catalog:** [`../docs/PROVIDERS.md`](../docs/PROVIDERS.md)
- **Funnel / monetization framing:** GitHub Discussion #38.

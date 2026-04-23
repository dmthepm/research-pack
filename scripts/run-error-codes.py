#!/usr/bin/env python3
"""In-process harness — trigger every one of the 7 envelope ``error.code``
values deterministically and capture the resulting envelope.

Two of the codes (``ssrf_rejected``, ``no_provider_succeeded``) fire
through the public CLI on cold inputs. The remaining five
(``network_timeout``, ``blocked_by_antibot``, ``response_too_large``,
``fixture_path_traversal_rejected``, ``misconfigured_provider``) need
either a slow / blocked / oversize upstream, a malicious ``--mock``
slug, or an already-failed primary provider — all brittle to reproduce
from CLI alone. This harness drives ``companyctx.core.run`` with a
synthetic ``ProviderBase`` that emits the exact prefix string the
production classifier reads (``companyctx/core.py:_classify_error_code``),
plus the real fixture-path validator for
``fixture_path_traversal_rejected``.

The point is not to test internal code paths — those are covered in
``tests/test_envelope_error_codes.py``. The point is to give an
external auditor (or a partner-integration validator) one runnable script
that proves every public ``EnvelopeErrorCode`` fires end-to-end with
expected envelope shape, and to commit the envelope evidence.

Usage::

    PYTHONPATH=. python3 scripts/run-error-codes.py
    PYTHONPATH=. python3 scripts/run-error-codes.py --out my.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from companyctx import core
from companyctx.providers.base import FetchContext
from companyctx.schema import ProviderRunMetadata


def make_failed_provider_class(
    error_msg: str,
    slug_tag: str = "fake_site_text",
    category: str = "site_text",
):
    """Build a parameter-free provider class that emits a controlled error."""

    class _Cls:
        slug = slug_tag
        version = "0.0.0"
        cost_hint = "free"

        def fetch(self, site: str, *, ctx: FetchContext):
            del site, ctx
            return None, ProviderRunMetadata(
                status="failed",
                latency_ms=1,
                error=error_msg,
                provider_version="0.0.0",
                cost_incurred=0,
            )

    _Cls.category = category
    _Cls.__name__ = f"FakeProvider_{slug_tag}"
    return _Cls


def make_not_configured_class(
    error_msg: str = "missing env var: COMPANYCTX_SMART_PROXY_URL",
    slug_tag: str = "fake_smart_proxy",
    category: str = "site_text",
):
    """Build a class that returns ``not_configured`` on ``fetch``.

    Category defaults to ``site_text`` (not ``smart_proxy``) because the
    orchestrator routes ``smart_proxy`` providers into Attempt 2 only when
    a primary site_text row failed first; using site_text here keeps the
    classifier on the single-failed-provider path that drives
    ``misconfigured_provider`` via ``failure_status == "not_configured"``.
    """

    class _Cls:
        slug = slug_tag
        version = "0.0.0"
        cost_hint = "per-call"

        def fetch(self, site: str, *, ctx: FetchContext):
            del site, ctx
            return None, ProviderRunMetadata(
                status="not_configured",
                latency_ms=0,
                error=error_msg,
                provider_version="0.0.0",
                cost_incurred=0,
            )

    _Cls.category = category
    _Cls.__name__ = f"NotConfiguredProvider_{slug_tag}"
    return _Cls


def _envelope_to_row(name: str, env, expected_code: str, mode: str) -> dict:
    err = env.error
    return {
        "trigger": name,
        "mode": mode,
        "expected_code": expected_code,
        "envelope_status": env.status,
        "actual_code": err.code if err else None,
        "message": err.message if err else None,
        "suggestion": err.suggestion if err else None,
        "matched": (err.code == expected_code) if err else False,
    }


def trigger_all() -> list[dict]:
    rows: list[dict] = []

    # Case 1 — ssrf_rejected (CLI-trivial; record library path too)
    env = core.run("http://10.0.0.1")
    rows.append(_envelope_to_row("ssrf_rejected (private IP)", env, "ssrf_rejected", "real-stack"))

    # Case 2 — no_provider_succeeded (default fallback when no prefix matches)
    env = core.run(
        "acme.test",
        providers={
            "fake": make_failed_provider_class(  # type: ignore[arg-type]
                "generic upstream failure"
            )
        },
    )
    rows.append(
        _envelope_to_row(
            "no_provider_succeeded (generic failure)",
            env,
            "no_provider_succeeded",
            "synthetic-provider",
        )
    )

    # Case 3 — network_timeout
    env = core.run(
        "acme.test",
        providers={
            "fake": make_failed_provider_class(  # type: ignore[arg-type]
                "connect timeout after 10s"
            )
        },
    )
    rows.append(
        _envelope_to_row(
            "network_timeout (timeout substring)", env, "network_timeout", "synthetic-provider"
        )
    )

    # Case 4 — blocked_by_antibot — same prefix the real provider emits
    env = core.run(
        "acme.test",
        providers={
            "fake": make_failed_provider_class(  # type: ignore[arg-type]
                "blocked_by_antibot (HTTP 403)"
            )
        },
    )
    rows.append(
        _envelope_to_row(
            "blocked_by_antibot (HTTP 403 prefix)", env, "blocked_by_antibot", "synthetic-provider"
        )
    )

    # Case 5 — response_too_large
    env = core.run(
        "acme.test",
        providers={
            "fake": make_failed_provider_class(  # type: ignore[arg-type]
                "response_too_large: content-length 31457280 exceeds 10485760"
            )
        },
    )
    rows.append(
        _envelope_to_row(
            "response_too_large (size cap)", env, "response_too_large", "synthetic-provider"
        )
    )

    # Case 6 — fixture_path_traversal_rejected — real fixture-path validator
    env = core.run("../etc/passwd", mock=True, fixtures_dir="fixtures")
    rows.append(
        _envelope_to_row(
            "fixture_path_traversal_rejected (fixture slug ..)",
            env,
            "fixture_path_traversal_rejected",
            "real-stack-mock",
        )
    )

    # Case 7 — misconfigured_provider — only-provider returns not_configured
    env = core.run(
        "acme.test",
        providers={"fake_proxy": make_not_configured_class()},  # type: ignore[arg-type]
    )
    rows.append(
        _envelope_to_row(
            "misconfigured_provider (not_configured only)",
            env,
            "misconfigured_provider",
            "synthetic-provider",
        )
    )

    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--out",
        default="research/2026-04-22-v0.2-joel-integration-error-codes.jsonl",
        help="output JSONL path",
    )
    args = ap.parse_args()

    rows = trigger_all()
    out = Path(args.out)
    out.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )

    matched = sum(1 for r in rows if r["matched"])
    print(f"wrote {len(rows)} rows -> {out}")
    print(f"codes triggered: {matched}/{len(rows)}")
    for r in rows:
        flag = "OK " if r["matched"] else "MISS"
        print(
            f"  [{flag}] {r['trigger']:55s}  "
            f"expected={r['expected_code']:30s}  actual={r['actual_code']}"
        )


if __name__ == "__main__":
    main()

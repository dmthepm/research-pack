"""Orchestrator behavior: status aggregation, graceful-partial, determinism."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Literal, cast

import pytest
from typer.testing import CliRunner

from companyctx import core
from companyctx.cli import app
from companyctx.providers.base import FetchContext, ProviderBase
from companyctx.providers.site_text_trafilatura import Provider as TrafilaturaProvider
from companyctx.schema import (
    Envelope,
    MediaMention,
    MentionsSignals,
    ProviderRunMetadata,
    SiteSignals,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
FIXED_WHEN = datetime(2026, 4, 20, tzinfo=timezone.utc)
FETCHED_AT_RE = re.compile(rb'"fetched_at":\s*"[^"]+"')


def _reg(**mapping: type) -> dict[str, type[ProviderBase]]:
    """Narrow test-provider classes to the ProviderBase Protocol for mypy.

    Every class passed here is runtime-checkable against ``ProviderBase``; the
    cast is just a typing convenience so ``core.run(providers=...)`` accepts
    them without each test growing its own cast boilerplate.
    """
    return cast("dict[str, type[ProviderBase]]", dict(mapping))


class _AlwaysOk:
    slug: ClassVar[str] = "always_ok"
    category: ClassVar[Literal["site_text"]] = "site_text"
    cost_hint: ClassVar[Literal["free"]] = "free"
    version: ClassVar[str] = "0.1.0"

    def fetch(
        self, site: str, *, ctx: FetchContext
    ) -> tuple[SiteSignals | None, ProviderRunMetadata]:
        return (
            SiteSignals(homepage_text=f"hello {site}"),
            ProviderRunMetadata(status="ok", latency_ms=0, provider_version=self.version),
        )


class _AlwaysFail:
    slug: ClassVar[str] = "always_fail"
    category: ClassVar[Literal["site_text"]] = "site_text"
    cost_hint: ClassVar[Literal["free"]] = "free"
    version: ClassVar[str] = "0.1.0"

    def fetch(
        self, site: str, *, ctx: FetchContext
    ) -> tuple[SiteSignals | None, ProviderRunMetadata]:
        return None, ProviderRunMetadata(
            status="failed",
            latency_ms=42,
            error="blocked_by_antibot (HTTP 403)",
            provider_version=self.version,
        )


class _Explodes:
    """Provider that raises — the orchestrator must wrap it into a failed row."""

    slug: ClassVar[str] = "explodes"
    category: ClassVar[Literal["site_text"]] = "site_text"
    cost_hint: ClassVar[Literal["free"]] = "free"
    version: ClassVar[str] = "0.1.0"

    def fetch(
        self, site: str, *, ctx: FetchContext
    ) -> tuple[SiteSignals | None, ProviderRunMetadata]:
        raise RuntimeError("provider internals misbehaved")


class _BadMetadata:
    slug: ClassVar[str] = "bad_metadata"
    category: ClassVar[Literal["site_text"]] = "site_text"
    cost_hint: ClassVar[Literal["free"]] = "free"
    version: ClassVar[str] = "0.1.0"

    def fetch(self, site: str, *, ctx: FetchContext) -> tuple[SiteSignals | None, object]:
        return SiteSignals(homepage_text=f"hello {site}"), {"status": "ok"}


class _MentionsOk:
    slug: ClassVar[str] = "mentions_ok"
    category: ClassVar[Literal["mentions"]] = "mentions"
    cost_hint: ClassVar[Literal["free"]] = "free"
    version: ClassVar[str] = "0.1.0"

    def fetch(
        self, site: str, *, ctx: FetchContext
    ) -> tuple[MentionsSignals | None, ProviderRunMetadata]:
        return (
            MentionsSignals(
                items=[
                    MediaMention(
                        title=f"{site} won an award",
                        url="https://example.com/award",
                        source="Example News",
                        kind="award",
                    )
                ]
            ),
            ProviderRunMetadata(status="ok", latency_ms=0, provider_version=self.version),
        )


class _FakeResponse:
    """Minimal stand-in for ``curl_cffi.requests.Response`` used by the
    network-path tests. Matches the streaming + header API the hardened
    ``_stealth_fetch`` relies on (see COX-23 / issue #53)."""

    status_code = 200

    def __init__(self, text: str) -> None:
        self._body = text.encode("utf-8")
        self.text = text
        self.headers: dict[str, str] = {}
        self.encoding = "utf-8"

    def iter_content(self, chunk_size: int = 8192) -> Any:
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def close(self) -> None:
        return None


def test_orchestrator_status_ok_when_all_providers_ok() -> None:
    env = core.run(
        "example.com",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(always_ok=_AlwaysOk),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "ok"
    assert env.error is None
    assert env.provenance["always_ok"].status == "ok"


def test_orchestrator_status_partial_when_some_fail() -> None:
    env = core.run(
        "example.com",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(always_ok=_AlwaysOk, always_fail=_AlwaysFail),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "partial"
    assert env.error is not None
    assert env.error.code == "blocked_by_antibot"
    assert env.error.suggestion is not None
    assert env.provenance["always_ok"].status == "ok"
    assert env.provenance["always_fail"].status == "failed"


def test_orchestrator_status_degraded_when_all_fail() -> None:
    env = core.run(
        "example.com",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(always_fail=_AlwaysFail),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "degraded"
    assert env.error is not None
    assert env.error.code == "blocked_by_antibot"


def test_orchestrator_never_raises_when_provider_explodes() -> None:
    env = core.run(
        "example.com",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(explodes=_Explodes),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "degraded"
    row = env.provenance["explodes"]
    assert row.status == "failed"
    assert row.error is not None
    assert "RuntimeError" in row.error


def test_orchestrator_never_raises_when_discovery_explodes(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> dict[str, type[ProviderBase]]:
        raise RuntimeError("discover blew up")

    monkeypatch.setattr(core, "discover", _boom)
    env = core.run("example.com", mock=True, fixtures_dir=FIXTURES_DIR, fetched_at=FIXED_WHEN)
    assert env.status == "degraded"
    row = env.provenance["_provider_discovery"]
    assert row.status == "failed"
    assert row.error is not None
    assert "discover blew up" in row.error


def test_orchestrator_never_raises_when_provider_metadata_is_malformed() -> None:
    env = core.run(
        "example.com",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(bad_metadata=_BadMetadata),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "degraded"
    row = env.provenance["bad_metadata"]
    assert row.status == "failed"
    assert row.error is not None
    assert "invalid metadata" in row.error


def test_orchestrator_graceful_partial_on_missing_fixture() -> None:
    """A slug with no fixture dir → provider returns failed; envelope stays well-formed."""
    env = core.run(
        "no-such-site.example",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "degraded"
    assert env.data.pages is None
    assert env.error is not None
    provider_error = env.provenance["site_text_trafilatura"].error
    assert provider_error is not None
    assert "fixture" in provider_error
    assert env.error.code in {"no_provider_succeeded", "fixture_path_traversal_rejected"}


@pytest.mark.parametrize(
    "reason",
    [
        "blocked_by_antibot (HTTP 403)",
        "network error: Timeout",
        "fm13-custom-reason",
    ],
)
def test_fixture_block_sentinel_round_trips_as_degraded(reason: str, tmp_path: Path) -> None:
    """`fixture-block.txt` raises _BlockedError with its content as the reason.

    Provider already maps _BlockedError → ProviderRunMetadata.status="failed"
    with `error=<reason>`; when it's the only provider, the envelope status
    aggregates to "degraded".
    """
    slug = "blockfix"
    site_dir = tmp_path / slug
    site_dir.mkdir()
    (site_dir / "fixture-block.txt").write_text(reason, encoding="utf-8")

    env = core.run(
        f"{slug}.example",
        mock=True,
        fixtures_dir=tmp_path,
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "degraded"
    row = env.provenance["site_text_trafilatura"]
    assert row.status == "failed"
    assert row.error == reason
    assert env.error is not None
    assert env.error.message == reason
    assert env.data.pages is None


def test_fixture_block_sentinel_takes_precedence_over_homepage(tmp_path: Path) -> None:
    """If both files exist, the block sentinel wins — homepage is not read."""
    slug = "blockfix"
    site_dir = tmp_path / slug
    site_dir.mkdir()
    (site_dir / "fixture-block.txt").write_text("blocked_by_antibot (HTTP 403)", encoding="utf-8")
    (site_dir / "homepage.html").write_text("<html><body>should not appear</body></html>")

    env = core.run(
        f"{slug}.example",
        mock=True,
        fixtures_dir=tmp_path,
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "degraded"
    assert env.data.pages is None
    assert env.provenance["site_text_trafilatura"].error == "blocked_by_antibot (HTTP 403)"


def test_mock_mode_rejects_invalid_fixture_slug() -> None:
    env = core.run(
        "../secrets",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "degraded"
    provider_error = env.provenance["site_text_trafilatura"].error
    assert provider_error is not None
    assert "invalid fixture slug" in provider_error


def test_mock_mode_populates_pages_homepage_text() -> None:
    env = core.run(
        "acme-bakery.example",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "ok"
    assert env.data.pages is not None
    assert "Acme Bakery" in env.data.pages.homepage_text
    assert env.data.pages.services == [
        "Custom cakes",
        "Catering",
        "Wholesale bread",
        "Pastry boxes",
    ]
    assert "WordPress" in env.data.pages.tech_stack


def test_orchestrator_merges_mentions_wrapper() -> None:
    env = core.run(
        "acme-bakery.example",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(mentions_ok=_MentionsOk, site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "ok"
    assert env.data.mentions is not None
    assert env.data.mentions.items[0].kind == "award"


def test_provider_respects_robots_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "companyctx.providers.site_text_trafilatura.is_allowed",
        lambda url, user_agent: False,
    )
    env = core.run(
        "https://example.com",
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "degraded"
    provider_error = env.provenance["site_text_trafilatura"].error
    assert provider_error == "blocked_by_robots"


def test_ignore_robots_bypasses_robots_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "companyctx.providers.site_text_trafilatura.is_allowed",
        lambda url, user_agent: False,
    )
    # Keep the body comfortably above ``EMPTY_RESPONSE_BYTES`` (COX-44
    # / COX-52, now 1024) so this test stays about the robots-bypass
    # path, not the empty-response honesty check.
    marker_sentence = "Hello from the ignore-robots smoke path."
    body_paragraphs = (
        f"{marker_sentence} This body is intentionally long enough to clear the "
        "v0.4.0 empty-response cutoff so the envelope lands on status=ok and this "
        "test keeps probing the robots-bypass wiring, not the thin-body gate.",
        "A legitimate homepage easily carries multiple paragraphs of "
        "differentiator, audience, and credentials prose; anything much shorter "
        "would rightly trip empty_response under the v0.4.0 floor raise for FM-7.",
        "This fixture stands in for a normal SSR-rendered page returned by the "
        "zero-key provider. The business is fictional, based in Portland, and has "
        "operated in the metro area for over a decade with a team of nine.",
        "We work with homeowners, small businesses, and repeat commercial "
        "accounts. Every engagement starts with a site walkthrough and a written "
        "scope so there are no surprises on invoice day.",
        "We publish before-and-after galleries, customer reviews, and project "
        "case studies on the site so prospective clients can see the actual "
        "work our team has delivered, not just marketing renders. The extra "
        "paragraph is padding prose that keeps the extracted body above the "
        "FM-7 floor even after trafilatura trims boilerplate.",
    )
    body_html = "".join(f"<p>{p}</p>" for p in body_paragraphs)
    monkeypatch.setattr(
        "companyctx.providers.site_text_trafilatura.requests.get",
        lambda *args, **kwargs: _FakeResponse(f"<html><body>{body_html}</body></html>"),
    )
    env = core.run(
        "https://example.com",
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        ignore_robots=True,
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "ok"
    assert env.data.pages is not None
    assert marker_sentence in env.data.pages.homepage_text


def test_provider_rejects_unsupported_scheme() -> None:
    env = core.run(
        "file:///etc/passwd",
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "degraded"
    provider_error = env.provenance["site_text_trafilatura"].error
    assert provider_error is not None
    assert "unsupported scheme" in provider_error


def test_cli_mock_output_is_byte_identical_modulo_fetched_at() -> None:
    runner = CliRunner()
    result1 = runner.invoke(
        app,
        [
            "fetch",
            "acme-bakery.example",
            "--mock",
            "--json",
            "--fixtures-dir",
            str(FIXTURES_DIR),
        ],
    )
    result2 = runner.invoke(
        app,
        [
            "fetch",
            "acme-bakery.example",
            "--mock",
            "--json",
            "--fixtures-dir",
            str(FIXTURES_DIR),
        ],
    )
    assert result1.exit_code == 0, result1.stdout
    assert result2.exit_code == 0, result2.stdout
    assert _scrub_fetched_at(result1.stdout.encode("utf-8")) == _scrub_fetched_at(
        result2.stdout.encode("utf-8")
    )


def _scrub_fetched_at(raw: bytes) -> bytes:
    return FETCHED_AT_RE.sub(b'"fetched_at": "<scrubbed>"', raw)


def test_cli_fetch_emits_schema_valid_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    # Explicitly keep GOOGLE_PLACES_API_KEY unset: the orchestrator skips
    # the unconfigured direct-API provider so the zero-key default path
    # stays at status=ok (the README's load-bearing promise).
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "fetch",
            "acme-bakery.example",
            "--mock",
            "--json",
            "--fixtures-dir",
            str(FIXTURES_DIR),
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    # Round-trip the stdout JSON through the envelope to prove schema validity.
    env = Envelope.model_validate(payload)
    assert env.status == "ok"
    assert env.data.pages is not None
    assert env.data.pages.homepage_text
    # No Places key -> provider skipped entirely (no provenance row).
    assert "reviews_google_places" not in env.provenance


def test_cli_fetch_with_places_key_populates_reviews(monkeypatch: pytest.MonkeyPatch) -> None:
    # With the Places key set, the --mock path reads the fixture's
    # ``google_places.json`` and fills data.reviews deterministically.
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "fetch",
            "acme-bakery.example",
            "--mock",
            "--json",
            "--fixtures-dir",
            str(FIXTURES_DIR),
        ],
    )
    assert result.exit_code == 0, result.stdout
    env = Envelope.model_validate(json.loads(result.stdout))
    assert env.status == "ok"
    assert env.data.reviews is not None
    assert env.data.reviews.source == "reviews_google_places"


def test_cli_fetch_partial_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        core,
        "discover",
        lambda: _reg(always_ok=_AlwaysOk, always_fail=_AlwaysFail),
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "fetch",
            "example.com",
            "--mock",
            "--json",
            "--fixtures-dir",
            str(FIXTURES_DIR),
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    env = Envelope.model_validate(payload)
    assert env.status == "partial"
    assert env.error is not None
    assert env.error.suggestion is not None


def test_cli_fetch_partial_exits_zero_on_missing_fixture() -> None:
    """Missing fixture → partial envelope (smart-proxy advertises recovery), exit 0.

    The ``smart_proxy_http`` provider is discovered via entry points but
    returns ``not_configured`` without ``COMPANYCTX_SMART_PROXY_URL`` — the
    aggregator promotes the top-level status from ``degraded`` to ``partial``
    so the envelope's ``suggestion`` can name the config-based escape hatch.
    """
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "fetch",
            "nonexistent-site.example",
            "--mock",
            "--json",
            "--fixtures-dir",
            str(FIXTURES_DIR),
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    env = Envelope.model_validate(payload)
    assert env.status == "partial"
    assert env.error is not None
    assert env.error.suggestion is not None


def test_cli_validate_accepts_round_tripped_envelope(tmp_path: Path) -> None:
    env = core.run(
        "acme-bakery.example",
        mock=True,
        fixtures_dir=FIXTURES_DIR,
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    path = tmp_path / "env.json"
    path.write_text(env.model_dump_json(indent=2), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 0, result.stdout


def test_cli_validate_rejects_extra_field(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "status": "ok",
                "data": {"site": "x", "fetched_at": FIXED_WHEN.isoformat(), "bogus": 1},
                "provenance": {},
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 1


@pytest.mark.parametrize(
    ("homepage_html", "expect_empty"),
    [
        # Zero visible body — trafilatura returns nothing, BS fallback also
        # yields "". 0 < 1024 → empty_response trips.
        ("<!DOCTYPE html><html><head></head><body></body></html>", True),
        # Login-wall stub shape: visible text is well under the 1024-byte
        # v0.4.0 cutoff (also under the prior 64-byte floor).
        ("<html><body><p>Please sign in</p></body></html>", True),
        # FM-7 thin-body shape: ~500 bytes of visible prose — cleared the
        # old 64-byte floor (would have been silent-success under v0.3.0)
        # but fails the v0.4.0 1024-byte floor. This case is the reason
        # COX-52 exists.
        (
            "<html><body><p>"
            + ("We bake bread in Portland. We cater weddings and supply local cafes. " * 7)
            + "</p></body></html>",
            True,
        ),
        # Legitimate brochure: comfortably above 1024 bytes of prose. Must
        # NOT trip the gate.
        (
            "<html><body><p>"
            + (
                "We bake bread in Portland. We cater weddings and supply local cafes "
                "with sourdough loaves, brioche buns, and seasonal specials. Our team "
                "of nine has served the city for over a decade, delivering to shops "
                "from St. Johns to Sellwood every morning before seven. Visit our "
                "Division Street location for fresh pastries and espresso. "
            )
            * 5
            + "</p></body></html>",
            False,
        ),
    ],
)
def test_empty_response_trips_honesty_check(
    tmp_path: Path, homepage_html: str, expect_empty: bool
) -> None:
    """COX-44 / COX-52 — extracted text below EMPTY_RESPONSE_BYTES surfaces
    as ``error.code == "empty_response"`` instead of a silent ``status: ok``.
    Above the cutoff the envelope stays ``ok``. Regression guard on the
    exact threshold behavior: v0.4.0 raises the floor 64 → 1024 so the
    FM-7 thin-body class (status ok + <1 KiB of extracted text) now
    surfaces honestly.
    """
    slug = "emptyprobe"
    site_dir = tmp_path / slug
    site_dir.mkdir()
    (site_dir / "homepage.html").write_text(homepage_html, encoding="utf-8")

    env = core.run(
        f"{slug}.example",
        mock=True,
        fixtures_dir=tmp_path,
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    if expect_empty:
        assert env.status == "degraded"
        assert env.error is not None
        assert env.error.code == "empty_response"
        assert env.error.suggestion is not None
        assert "HTTP 200" in env.error.suggestion
        row = env.provenance["site_text_trafilatura"]
        assert row.status == "failed"
        assert row.error == "empty_response"
        assert env.data.pages is None
    else:
        assert env.status == "ok"
        assert env.error is None
        assert env.data.pages is not None
        assert env.data.pages.homepage_text


def test_empty_response_applies_to_smart_proxy_recovery(tmp_path: Path) -> None:
    """Attempt-2 must not launder silent-success past the honesty gate.

    Primary zero-key provider fails with ``blocked_by_antibot`` — an error
    that IS recoverable via smart-proxy per the waterfall. The proxy then
    returns an HTTP 200 with an empty body. Before the fix this landed
    ``status: "ok"`` with ``pages.homepage_text: ""``. After the fix the
    recovery path treats the empty body as ``empty_response`` on the proxy
    row, no recovery happens, and the envelope surfaces the honest shape.
    """

    class _BlockedPrimary:
        slug: ClassVar[str] = "site_text_blocked"
        category: ClassVar[Literal["site_text"]] = "site_text"
        cost_hint: ClassVar[Literal["free"]] = "free"
        version: ClassVar[str] = "0.1.0"

        def fetch(
            self, site: str, *, ctx: FetchContext
        ) -> tuple[SiteSignals | None, ProviderRunMetadata]:
            return None, ProviderRunMetadata(
                status="failed",
                latency_ms=0,
                error="blocked_by_antibot (HTTP 403)",
                provider_version=self.version,
            )

    class _EmptyBodyProxy:
        slug: ClassVar[str] = "smart_proxy_empty"
        category: ClassVar[Literal["smart_proxy"]] = "smart_proxy"
        cost_hint: ClassVar[Literal["per-call"]] = "per-call"
        version: ClassVar[str] = "0.1.0"

        def fetch(self, url: str, *, ctx: FetchContext) -> tuple[bytes | None, ProviderRunMetadata]:
            return b"<!DOCTYPE html><html><head></head><body></body></html>", (
                ProviderRunMetadata(status="ok", latency_ms=1, provider_version=self.version)
            )

    env = core.run(
        "any.example",
        mock=True,
        fixtures_dir=tmp_path,
        providers=_reg(
            site_text_blocked=_BlockedPrimary,
            smart_proxy_empty=_EmptyBodyProxy,
        ),
        fetched_at=FIXED_WHEN,
    )
    proxy_row = env.provenance["smart_proxy_empty"]
    assert proxy_row.status == "failed"
    assert proxy_row.error == "empty_response"
    assert env.data.pages is None
    assert env.status in {"degraded", "partial"}
    # Terminal-signal rule: the primary row carries
    # ``blocked_by_antibot`` (the trigger for the proxy retry), but the
    # waterfall's terminal failure is the proxy's empty body. Envelope-
    # level ``error.code`` must reflect that, otherwise agents branching
    # on the envelope see a stale antibot signal and the
    # smart-proxy-based suggestion when the proxy was actually run.
    assert env.error is not None
    assert env.error.code == "empty_response"
    assert env.error.suggestion is not None
    assert "HTTP 200" in env.error.suggestion


def test_empty_response_gate_measures_utf8_bytes_not_chars(tmp_path: Path) -> None:
    """Multibyte prose must not false-positive as empty.

    Under the v0.4.0 1024-byte floor, a ~400-char CJK homepage that
    encodes to ~1200 UTF-8 bytes must stay ``ok`` — counting
    ``len(text)`` instead of ``len(text.encode("utf-8"))`` would
    mis-flag it as empty_response because the char count (400) is under
    the byte threshold (1024). The gate has to measure bytes.
    """
    slug = "cjkprobe"
    site_dir = tmp_path / slug
    site_dir.mkdir()
    # 400 katakana chars = 1200 UTF-8 bytes: char count under 1024,
    # byte count over. The gate must read bytes to keep this ``ok``.
    body_text = "カタカナ" * 100  # 400 chars, 1200 bytes
    (site_dir / "homepage.html").write_text(
        f"<html><body><p>{body_text}</p></body></html>", encoding="utf-8"
    )

    env = core.run(
        f"{slug}.example",
        mock=True,
        fixtures_dir=tmp_path,
        providers=_reg(site_text_trafilatura=TrafilaturaProvider),
        fetched_at=FIXED_WHEN,
    )
    assert env.status == "ok", env.error
    assert env.data.pages is not None
    assert body_text in env.data.pages.homepage_text


def test_empty_response_does_not_trigger_smart_proxy_retry() -> None:
    """A failed site_text row with ``error == "empty_response"`` must not be
    routed to the smart-proxy recovery path — the fetch already worked, the
    site returned nothing. Automatic retry on empty is explicitly out of
    scope for COX-44; agents decide what to do.
    """

    class _EmptyResponseProvider:
        slug: ClassVar[str] = "site_text_empty"
        category: ClassVar[Literal["site_text"]] = "site_text"
        cost_hint: ClassVar[Literal["free"]] = "free"
        version: ClassVar[str] = "0.1.0"

        def fetch(
            self, site: str, *, ctx: FetchContext
        ) -> tuple[SiteSignals | None, ProviderRunMetadata]:
            return None, ProviderRunMetadata(
                status="failed",
                latency_ms=0,
                error="empty_response",
                provider_version=self.version,
            )

    proxy_calls: list[str] = []

    class _RecordingProxy:
        slug: ClassVar[str] = "smart_proxy_record"
        category: ClassVar[Literal["smart_proxy"]] = "smart_proxy"
        cost_hint: ClassVar[Literal["per-call"]] = "per-call"
        version: ClassVar[str] = "0.1.0"

        def fetch(self, url: str, *, ctx: FetchContext) -> tuple[bytes | None, ProviderRunMetadata]:
            proxy_calls.append(url)
            return b"<html><body>recovered</body></html>", ProviderRunMetadata(
                status="ok", latency_ms=1, provider_version=self.version
            )

    env = core.run(
        "any.example",
        mock=True,
        providers=_reg(
            site_text_empty=_EmptyResponseProvider,
            smart_proxy_record=_RecordingProxy,
        ),
        fetched_at=FIXED_WHEN,
    )
    assert proxy_calls == []
    assert env.status == "degraded"
    assert env.error is not None
    assert env.error.code == "empty_response"


def test_cli_providers_list_shows_registered_provider() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["providers", "list"])
    assert result.exit_code == 0, result.stdout
    assert "site_text_trafilatura" in result.stdout

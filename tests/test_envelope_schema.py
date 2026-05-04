"""Schema round-trip + ``extra=\"forbid\"`` invariants for the envelope."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from companyctx.schema import (
    CompanyContext,
    Envelope,
    EnvelopeError,
    FundingRound,
    HeuristicSignals,
    MediaMention,
    MentionsSignals,
    ProviderRunMetadata,
    ReviewsSignals,
    SiteSignals,
    SocialSignals,
)


def _fixed_dt() -> datetime:
    return datetime(2026, 4, 20, tzinfo=timezone.utc)


def test_envelope_round_trips_through_json() -> None:
    env = Envelope(
        schema_version="0.5.0",
        status="ok",
        data=CompanyContext(
            site="example.com",
            fetched_at=_fixed_dt(),
            pages=SiteSignals(
                homepage_text="hi",
                about_text="about",
                services=["a", "b"],
                tech_stack=["WordPress"],
            ),
            reviews=ReviewsSignals(count=10, rating=4.5, source="reviews_google_places"),
            social=SocialSignals(handles={"instagram": "@ex"}),
            signals=HeuristicSignals(team_size_claim="team of 6"),
            mentions=MentionsSignals(
                items=[
                    MediaMention(
                        title="Award",
                        url="https://example.com/award",
                        source="Example News",
                        kind="award",
                    )
                ]
            ),
        ),
        provenance={
            "site_text_trafilatura": ProviderRunMetadata(
                status="ok", latency_ms=12, provider_version="0.1.0"
            )
        },
    )
    serialized = env.model_dump_json()
    reparsed = Envelope.model_validate_json(serialized)
    assert reparsed == env


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            Envelope,
            {
                "schema_version": "0.5.0",
                "status": "ok",
                "data": {"site": "x", "fetched_at": _fixed_dt().isoformat()},
                "provenance": {},
            },
        ),
        (CompanyContext, {"site": "x", "fetched_at": _fixed_dt().isoformat()}),
        (SiteSignals, {"homepage_text": "x"}),
        (ReviewsSignals, {"count": 1, "source": "reviews_google_places"}),
        (SocialSignals, {}),
        (
            MediaMention,
            {
                "title": "Example",
                "url": "https://example.com/press",
                "source": "Example News",
                "kind": "press",
            },
        ),
        (FundingRound, {}),
        (HeuristicSignals, {}),
        (MentionsSignals, {}),
        (
            ProviderRunMetadata,
            {"status": "ok", "latency_ms": 0, "provider_version": "0.1.0"},
        ),
    ],
)
def test_models_reject_unknown_fields(model: type[object], payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**payload, "bogus": 1})  # type: ignore[attr-defined]


def test_provider_run_metadata_cost_incurred_defaults_to_zero() -> None:
    meta = ProviderRunMetadata(status="ok", latency_ms=0, provider_version="0.1.0")
    assert isinstance(meta.cost_incurred, int)
    assert meta.cost_incurred == 0


def test_provider_run_metadata_cost_incurred_explicit() -> None:
    meta = ProviderRunMetadata(
        status="ok",
        latency_ms=0,
        provider_version="0.1.0",
        cost_incurred=42,
    )
    assert isinstance(meta.cost_incurred, int)
    assert meta.cost_incurred == 42


def test_provider_run_metadata_is_frozen() -> None:
    meta = ProviderRunMetadata(status="ok", latency_ms=0, provider_version="0.1.0")
    with pytest.raises(ValidationError):
        meta.status = "failed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "payload",
    [
        # status=partial but no structured error.
        {
            "schema_version": "0.5.0",
            "status": "partial",
            "data": {"site": "x", "fetched_at": _fixed_dt().isoformat()},
            "provenance": {},
        },
        # status=degraded with a bare string in `error` (pre-v0.2 shape).
        {
            "schema_version": "0.5.0",
            "status": "degraded",
            "data": {"site": "x", "fetched_at": _fixed_dt().isoformat()},
            "provenance": {},
            "error": "no providers succeeded",
        },
        # status=ok must not carry an error.
        {
            "schema_version": "0.5.0",
            "status": "ok",
            "data": {"site": "x", "fetched_at": _fixed_dt().isoformat()},
            "provenance": {},
            "error": {
                "code": "no_provider_succeeded",
                "message": "should not be here",
            },
        },
    ],
)
def test_envelope_rejects_inconsistent_status_and_error(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        Envelope.model_validate(payload)


def test_envelope_schema_version_set_explicitly() -> None:
    env = Envelope(
        schema_version="0.5.0",
        status="ok",
        data=CompanyContext(site="x", fetched_at=_fixed_dt()),
        provenance={},
    )
    assert env.schema_version == "0.5.0"


def test_envelope_requires_schema_version_keyword() -> None:
    # COX-47: schema_version has no default. Omitting it at construction time
    # must raise — silent "upgrade" of a v0.1-shaped envelope is the bug.
    with pytest.raises(ValidationError) as excinfo:
        Envelope(  # type: ignore[call-arg]
            status="ok",
            data=CompanyContext(site="x", fetched_at=_fixed_dt()),
            provenance={},
        )
    assert "schema_version" in str(excinfo.value)


@pytest.mark.parametrize(
    "mutate",
    [
        # Field completely absent from the JSON payload (v0.1-shaped).
        lambda body: body,
        # Field present but explicit JSON null.
        lambda body: {**body, "schema_version": None},
        # Field present but empty string — fails the Literal["0.5.0"] check.
        lambda body: {**body, "schema_version": ""},
    ],
    ids=["missing_field", "null_value", "empty_string"],
)
def test_envelope_rejects_missing_or_empty_schema_version(
    mutate: object,
) -> None:
    # COX-47: the Literal rejected wrong values already; the default used to
    # accept missing ones. All three variants must now fail at parse time.
    body = {
        "status": "ok",
        "data": {"site": "x", "fetched_at": _fixed_dt().isoformat()},
        "provenance": {},
    }
    payload = json.dumps(mutate(body))  # type: ignore[operator]
    with pytest.raises(ValidationError) as excinfo:
        Envelope.model_validate_json(payload)
    assert "schema_version" in str(excinfo.value)


def test_envelope_rejects_v0_1_shaped_payload() -> None:
    # COX-47: A pre-v0.2 envelope (no schema_version, error as a bare string
    # instead of a structured EnvelopeError) must not silently validate. The
    # missing schema_version is the first tripwire; the bare-string error is
    # rejected too under extra="forbid" / type mismatch.
    v0_1_payload = {
        "status": "degraded",
        "data": {"site": "x", "fetched_at": _fixed_dt().isoformat()},
        "provenance": {},
        "error": "no providers succeeded",
        "suggestion": "configure a smart-proxy provider key",
    }
    with pytest.raises(ValidationError):
        Envelope.model_validate(v0_1_payload)


def test_envelope_error_requires_a_valid_code() -> None:
    with pytest.raises(ValidationError):
        EnvelopeError.model_validate({"code": "not_a_real_code", "message": "x"})


def test_envelope_error_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EnvelopeError.model_validate({"code": "ssrf_rejected", "message": "x", "bogus": 1})


def test_envelope_error_round_trips() -> None:
    env = Envelope(
        schema_version="0.5.0",
        status="partial",
        data=CompanyContext(site="x", fetched_at=_fixed_dt()),
        provenance={},
        error=EnvelopeError(
            code="blocked_by_antibot",
            message="blocked_by_antibot (HTTP 403)",
            suggestion="configure a smart-proxy",
        ),
    )
    reparsed = Envelope.model_validate_json(env.model_dump_json())
    assert reparsed.error is not None
    assert reparsed.error.code == "blocked_by_antibot"
    assert reparsed.error.suggestion == "configure a smart-proxy"

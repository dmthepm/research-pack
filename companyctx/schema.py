"""Pydantic v2 schema — the companyctx JSON contract.

The envelope is the product. Providers are replaceable; this shape is not.
Every model sets ``extra="forbid"`` so schema drift is loud. See
``docs/SCHEMA.md`` for the contract walkthrough and ``docs/SPEC.md`` for the
frozen spec snapshot.

v0.2.0 introduced the schema-locked envelope (top-level ``schema_version``
plus structured :class:`EnvelopeError`). v0.3.0 added two error codes:
``empty_response`` (so agents can branch on "site returned HTTP 200 with
effectively no content" instead of mistaking a silent-success for ok data)
and ``cache_corrupted`` (emitted on the ``--from-cache`` CLI path when the
cache opens but the row can't be deserialized). v0.4.0 closes the schema-
version drift the cache merge introduced, lands alongside the COX-52 FM-7
floor correction (``EMPTY_RESPONSE_BYTES`` 64 → 1024 — same ``Literal``
members, tighter threshold for ``empty_response``) and the COX-49
NXDOMAIN routing fix (``unsafe_url:dns_resolve_failure`` →
``no_provider_succeeded`` instead of ``ssrf_rejected``; no Literal
change, classifier-only), and renames ``path_traversal_rejected`` →
``fixture_path_traversal_rejected`` to match the code's actual scope
(``--mock`` fixture-slug escapes only; it does not guard URL-path
traversal).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.4.0"

EnvelopeStatus = Literal["ok", "partial", "degraded"]
ProviderStatus = Literal["ok", "degraded", "failed", "not_configured"]
MentionKind = Literal["press", "podcast", "award", "mention"]
EnvelopeErrorCode = Literal[
    "ssrf_rejected",
    "network_timeout",
    "blocked_by_antibot",
    "fixture_path_traversal_rejected",
    "response_too_large",
    "no_provider_succeeded",
    "misconfigured_provider",
    "empty_response",
    "cache_corrupted",
]


class SiteSignals(BaseModel):
    """Homepage-derived observations, extractor-agnostic."""

    model_config = ConfigDict(extra="forbid")

    homepage_text: str
    about_text: str | None = None
    services: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)


class ReviewsSignals(BaseModel):
    """Aggregate review observations from a single source provider."""

    model_config = ConfigDict(extra="forbid")

    count: int
    rating: float | None = None
    source: str


class SocialSignals(BaseModel):
    """Platform handles and (where available) follower counts."""

    model_config = ConfigDict(extra="forbid")

    handles: dict[str, str] = Field(default_factory=dict)
    follower_counts: dict[str, int] = Field(default_factory=dict)


class MediaMention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    source: str
    kind: MentionKind
    date: datetime | None = None


class FundingRound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_type: str | None = None
    amount_usd: int | None = None
    announced_at: datetime | None = None


class HeuristicSignals(BaseModel):
    """Raw, uninferred cross-reference observations."""

    model_config = ConfigDict(extra="forbid")

    team_size_claim: str | None = None
    linkedin_employee_count: int | None = None
    hiring_page_active: bool | None = None
    last_funding_round: FundingRound | None = None
    copyright_year: int | None = None
    last_blog_post_at: datetime | None = None
    tech_vs_claim_mismatches: list[str] = Field(default_factory=list)


class MentionsSignals(BaseModel):
    """Collection wrapper so providers can attach their own source metadata later."""

    model_config = ConfigDict(extra="forbid")

    items: list[MediaMention] = Field(default_factory=list)


class ProviderRunMetadata(BaseModel):
    """Per-provider provenance row attached to every envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ProviderStatus
    latency_ms: int
    error: str | None = None
    provider_version: str
    cost_incurred: int = 0
    """Cost charged by this attempt, in US cents. Zero-key providers stay 0."""


class CompanyContext(BaseModel):
    """Schema payload. Every field except site+fetched_at is optional."""

    model_config = ConfigDict(extra="forbid")

    site: str = Field(..., description="Prospect hostname or URL.")
    fetched_at: datetime = Field(..., description="UTC timestamp of the run.")

    pages: SiteSignals | None = None
    reviews: ReviewsSignals | None = None
    social: SocialSignals | None = None
    signals: HeuristicSignals | None = None
    mentions: MentionsSignals | None = None


class EnvelopeError(BaseModel):
    """Structured envelope error — machine-readable code + human-readable message.

    Agents branch on :attr:`code`; humans read :attr:`message`. :attr:`suggestion`
    is an actionable next step (e.g. "configure COMPANYCTX_SMART_PROXY_URL").

    Codes are a closed set. Adding, renaming, or removing a code all bump
    :data:`SCHEMA_VERSION`. In the pre-1.0 (0.x) series, any closed-set
    change — additive or breaking — lands as a MINOR bump; rename and
    removal are called out as BREAKING in CHANGELOG. Post-1.0, renames
    and removals will require a MAJOR bump.
    """

    model_config = ConfigDict(extra="forbid")

    code: EnvelopeErrorCode
    message: str
    suggestion: str | None = None


class Envelope(BaseModel):
    """Top-level JSON contract. Every ``fetch`` run emits exactly one of these."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.4.0"]
    status: EnvelopeStatus
    data: CompanyContext
    provenance: dict[str, ProviderRunMetadata] = Field(default_factory=dict)
    error: EnvelopeError | None = None

    @model_validator(mode="after")
    def validate_status_fields(self) -> Envelope:
        """Keep the top-level narrative honest and machine-checkable."""
        if self.status == "ok":
            if self.error is not None:
                raise ValueError('status="ok" must not include an error')
            return self
        if self.error is None:
            raise ValueError('status!="ok" requires a structured error')
        return self


__all__ = [
    "SCHEMA_VERSION",
    "CompanyContext",
    "Envelope",
    "EnvelopeError",
    "EnvelopeErrorCode",
    "EnvelopeStatus",
    "FundingRound",
    "HeuristicSignals",
    "MediaMention",
    "MentionKind",
    "MentionsSignals",
    "ProviderRunMetadata",
    "ProviderStatus",
    "ReviewsSignals",
    "SiteSignals",
    "SocialSignals",
]

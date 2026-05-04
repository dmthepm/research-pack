"""companyctx — deterministic B2B company context router. Zero keys. Schema-locked JSON."""

from __future__ import annotations

from companyctx.schema import (
    SCHEMA_VERSION,
    CompanyContext,
    Envelope,
    EnvelopeError,
    EnvelopeErrorCode,
    EnvelopeStatus,
    FundingRound,
    HeuristicSignals,
    MediaMention,
    MentionKind,
    MentionsSignals,
    ProviderRunMetadata,
    ProviderStatus,
    ReviewsSignals,
    SiteSignals,
    SocialSignals,
)

__version__ = "0.5.0"

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
    "__version__",
]

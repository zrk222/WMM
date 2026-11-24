"""Resolve fixed private HTTP domains without eager feature imports."""

from typing import cast

from .http_types import DomainPost


def owner_domain_post(parts: list[str]) -> DomainPost | None:
    """Resolve only fixed private domain modules, retaining lazy imports."""
    if len(parts) < 4 or parts[:2] != ["api", "apps"]:
        return None
    module = {
        "drive": "drive_http",
        "media": "managed_media_http",
        "funnels": "funnel_http",
        "discovery": "discovery_http",
        "organic-video": "organic_video_http",
        "packaging": "packaging_http",
        "campaigns": "campaign_http",
        "campaign-monitor": "campaign_monitor_http",
        "campaign-owner-reports": "campaign_owner_reports",
        "apple-analytics": "apple_metrics_http",
        "onesignal": "onesignal_setup_http",
        "authority-expiry": "authority_expiry_http",
        "marketing-review": "marketing_review_http",
        "observational-campaign": "observational_campaign_http",
    }.get(parts[3])
    if module is None:
        return None
    from importlib import import_module

    return cast(DomainPost, import_module("." + module, __package__).post)

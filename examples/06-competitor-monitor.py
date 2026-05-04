"""06-competitor-monitor.py — daily competitor diff-and-alert.

Run this on a cron (daily, hourly, whatever). Each run fetches the
target domain, compares the envelope to the last saved baseline, and
prints only the business-meaningful changes — new services, tech-stack
additions or removals, review-count step changes, copyright-year
updates, new social handles.

Because the envelope has ``extra="forbid"``, the diff is stable by
construction. You don't get "CSS class renamed" false positives; you
get exactly the signals that matter for positioning.

Usage:
    python 06-competitor-monitor.py rival-startup.com
    python 06-competitor-monitor.py rival-startup.com --mock   # fixture-backed demo

The baseline is stored as ``.competitor-state-<site>.json`` in the
current working directory on the first run. Delete it to re-baseline.
(The dotfile prefix keeps it out of most ``ls`` and ``git status``
noise — and the repo's ``.gitignore`` excludes it too.)
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from companyctx.core import run


def _load_baseline(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open() as fh:
        loaded: dict[str, Any] = json.load(fh)
        return loaded


def _save_baseline(path: Path, data: dict[str, Any]) -> None:
    with path.open("w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True, default=str)


def _set(data: dict[str, Any] | None, *keys: str) -> set[str]:
    """Safe nested lookup that returns a set of strings from a list field."""
    cursor: Any = data or {}
    for key in keys:
        if not isinstance(cursor, dict):
            return set()
        cursor = cursor.get(key)
    return set(cursor) if isinstance(cursor, list) else set()


def _scalar(data: dict[str, Any] | None, *keys: str) -> Any:
    cursor: Any = data or {}
    for key in keys:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


def diff(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Return human-readable change lines. Empty list = no meaningful change."""
    alerts: list[str] = []

    old_services, new_services = _set(old, "pages", "services"), _set(new, "pages", "services")
    if added := new_services - old_services:
        alerts.append(f"🆕 services added: {sorted(added)}")
    if removed := old_services - new_services:
        alerts.append(f"➖ services removed: {sorted(removed)}")

    old_tech, new_tech = _set(old, "pages", "tech_stack"), _set(new, "pages", "tech_stack")
    if added_tech := new_tech - old_tech:
        alerts.append(f"🛠  tech added: {sorted(added_tech)}")
    if removed_tech := old_tech - new_tech:
        alerts.append(f"🪓 tech removed: {sorted(removed_tech)}")

    old_rc, new_rc = _scalar(old, "reviews", "count"), _scalar(new, "reviews", "count")
    if isinstance(old_rc, int) and isinstance(new_rc, int) and new_rc - old_rc >= 10:
        alerts.append(f"📈 review count +{new_rc - old_rc} (now {new_rc})")

    old_cy, new_cy = (
        _scalar(old, "signals", "copyright_year"),
        _scalar(new, "signals", "copyright_year"),
    )
    if old_cy != new_cy and new_cy is not None:
        alerts.append(f"📆 copyright year: {old_cy} → {new_cy}")

    old_handles = (
        (_scalar(old, "social", "handles") or {})
        if isinstance(_scalar(old, "social", "handles"), dict)
        else {}
    )
    new_handles = (
        (_scalar(new, "social", "handles") or {})
        if isinstance(_scalar(new, "social", "handles"), dict)
        else {}
    )
    new_platforms = set(new_handles) - set(old_handles)
    if new_platforms:
        alerts.append(f"📣 new social handles: {sorted(new_platforms)}")

    return alerts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", help="Domain to monitor, e.g. rival-startup.com")
    parser.add_argument("--mock", action="store_true", help="Use fixtures corpus")
    args = parser.parse_args()

    state_path = Path.cwd() / f".competitor-state-{args.site.replace('/', '_')}.json"

    print(f"🕵️  Monitoring {args.site}...")
    # `fixtures/` lives at the repo root alongside `examples/`. We resolve it
    # relative to this script so the recipe runs from anywhere (including
    # `cd examples && python 06-...`). In real use (no --mock), the library
    # hits the network via the zero-key stealth fetcher and fixtures_dir is
    # None.
    fixtures_dir = (Path(__file__).resolve().parent.parent / "fixtures") if args.mock else None
    envelope = run(args.site, mock=args.mock, fixtures_dir=fixtures_dir)

    if envelope.status != "ok":
        print(f"⚠️  skipping diff — envelope status: {envelope.status}")
        if envelope.error:
            print(f"    code:       {envelope.error.code}")
            print(f"    message:    {envelope.error.message}")
            if envelope.error.suggestion:
                print(f"    suggestion: {envelope.error.suggestion}")
        return

    current = envelope.data.model_dump(mode="json")
    baseline = _load_baseline(state_path)

    if baseline is None:
        _save_baseline(state_path, current)
        print(f"📌 baseline saved to {state_path.name}. Re-run tomorrow to see the first diff.")
        return

    changes = diff(baseline, current)
    if not changes:
        print("✅ no meaningful changes since last run.")
    else:
        print(f"🚨 {len(changes)} change(s) detected on {args.site}:")
        for line in changes:
            print(f"   {line}")

    _save_baseline(state_path, current)
    print(f"💾 baseline refreshed ({datetime.now(timezone.utc).isoformat()})")


if __name__ == "__main__":
    main()


# --- EXPECTED OUTPUT (first run against fixture corpus, --mock) ---
# 🕵️  Monitoring acme-bakery...
# 📌 baseline saved to .competitor-state-acme-bakery.json. Re-run tomorrow to see the first diff.
#
# --- EXPECTED OUTPUT (subsequent run, no change) ---
# 🕵️  Monitoring acme-bakery...
# ✅ no meaningful changes since last run.
# 💾 baseline refreshed (2026-04-22T18:46:24.247102+00:00)
#
# --- EXPECTED OUTPUT (illustrative — live run against a competitor that actually changed) ---
# 🕵️  Monitoring rival-startup.com...
# 🚨 2 change(s) detected on rival-startup.com:
#    🆕 services added: ['AI consulting']
#    🛠  tech added: ['Next.js', 'Datadog']
# 💾 baseline refreshed (2026-04-22T09:15:02.184210+00:00)
#
# Note: review-count diffs, copyright-year diffs, and social-handle
# diffs rely on data.reviews / data.signals / data.social. On the
# current mock baseline those slots are still null, so the script diffs
# `pages.services` + `pages.tech_stack` only; the other branches wake up
# automatically once a provider fills the relevant slot.

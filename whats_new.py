"""Release notes for the dashboard's "What's new" panel.

The release workflow bundles changelog.json (scripts/build_changelog.py, from the
Conventional Commits between tags) into the image. The dashboard has no JavaScript
(its CSP allows none), so the panel is rendered server-side: it opens once after an
upgrade, and a cookie remembers the version the browser last saw."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CHANGELOG_PATH = Path(__file__).with_name("changelog.json")
SEEN_COOKIE = "noip_seen_version"
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


def _key(version: str | None) -> tuple[int, int, int] | None:
    match = _VERSION.match(version or "")
    if not match:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def load(path: Path | None = None) -> dict[str, Any]:
    """The bundled notes, or an empty set when missing/unreadable (dev builds)."""
    try:
        data = json.loads((path or CHANGELOG_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"releases": []}
    return data if isinstance(data, dict) else {"releases": []}


def since(data: dict[str, Any], seen: str | None) -> dict[str, Any]:
    """Releases newer than `seen` (all, newest five, when seen is None): user-facing
    ones listed, internal-only ones only named."""
    releases = data.get("releases") or []
    seen_key = _key(seen)
    if seen is not None and seen_key is None:
        return {"listed": [], "quiet": []}
    newer = [
        r
        for r in releases
        if seen_key is None or (_key(r.get("version")) or (0, 0, 0)) > seen_key
    ]
    listed = [r for r in newer if r.get("sections")]
    quiet = [r["version"] for r in newer if not r.get("sections")]
    if seen is None:
        return {"listed": listed[:5], "quiet": []}
    return {"listed": listed, "quiet": quiet}


def panel(
    data: dict[str, Any], current: str, seen: str | None, requested: bool
) -> dict[str, Any] | None:
    """What the panel shows now, or None. Auto-opens only after an upgrade that
    changed something users notice; `requested` (the version badge link) shows the
    latest releases regardless."""
    if requested:
        return {"since": None, **since(data, None)}
    seen_key, current_key = _key(seen), _key(current)
    if not seen or seen_key is None or current_key is None or seen_key >= current_key:
        return None
    shown = since(data, seen)
    return {"since": seen.lstrip("v"), **shown} if shown["listed"] else None

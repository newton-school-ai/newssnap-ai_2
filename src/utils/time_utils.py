"""NewsSnap AI - Time formatting and parsing utilities."""

from datetime import datetime, timedelta, timezone
from typing import Optional


def format_time_ago(dt: Optional[datetime]) -> str:
    """Format a datetime object into a human-readable relative time string.

    Examples:
        - "just now"
        - "5m ago"
        - "2h ago"
        - "3d ago"
        - "2w ago"

    Args:
        dt: The datetime to format.

    Returns:
        A human-readable relative time string.
    """
    if dt is None:
        return "recently"

    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    total_seconds = int((now - dt).total_seconds())

    if total_seconds < 60:
        return "just now"

    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"

    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"

    days = hours // 24
    if days < 7:
        return f"{days}d ago"

    weeks = days // 7
    if weeks < 4:
        return f"{weeks}w ago"

    months = days // 30
    if months < 12:
        return f"{months}mo ago"

    years = days // 365
    return f"{years}y ago"


def parse_time_range(time_range: Optional[str]) -> Optional[datetime]:
    """Parse a time range string into a UTC cutoff datetime.

    Supported formats:
        - "24h", "48h", "12h"
        - "1d", "2d", "7d", "30d"
        - "today"
        - "week"
        - "month"
        - integer hours (e.g. "24")

    Args:
        time_range: The string identifier for the time window.

    Returns:
        A timezone-aware UTC datetime cutoff, or None if unspecified or invalid.
    """
    if not time_range:
        return None

    cleaned = time_range.strip().lower()
    now = datetime.now(timezone.utc)

    if cleaned == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if cleaned in ("week", "7d"):
        return now - timedelta(days=7)
    if cleaned in ("month", "30d"):
        return now - timedelta(days=30)

    try:
        if cleaned.endswith("h"):
            hours = int(cleaned[:-1])
            return now - timedelta(hours=hours)
        if cleaned.endswith("d"):
            days = int(cleaned[:-1])
            return now - timedelta(days=days)
        if cleaned.isdigit():
            hours = int(cleaned)
            return now - timedelta(hours=hours)
    except ValueError:
        return None

    return None

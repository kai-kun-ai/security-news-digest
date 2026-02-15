"""RSS feed fetching and parsing."""

import feedparser
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateparser
from typing import List, Dict, Any


def fetch_feeds(feeds_config: List[Dict[str, str]], window_days: int = 3) -> List[Dict[str, Any]]:
    """Fetch articles from configured RSS feeds within the time window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    articles = []

    for feed_cfg in feeds_config:
        name = feed_cfg["name"]
        url = feed_cfg["url"]
        lang = feed_cfg.get("lang", "en")

        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            print(f"[WARN] Failed to fetch feed '{name}': {e}")
            continue

        for entry in parsed.entries:
            published = _parse_date(entry)
            if published and published < cutoff:
                continue

            article = {
                "title": entry.get("title", "").strip(),
                "url": entry.get("link", "").strip(),
                "summary": entry.get("summary", "").strip(),
                "published": published,
                "source_feed": name,
                "lang": lang,
                "source_name": _extract_source(entry),
            }
            articles.append(article)

    return articles


def _parse_date(entry) -> datetime | None:
    """Parse publication date from a feed entry."""
    for field in ("published", "updated", "created"):
        val = entry.get(field)
        if val:
            try:
                dt = dateparser.parse(val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, TypeError):
                continue
    return None


def _extract_source(entry) -> str:
    """Try to extract the original source name from the entry."""
    # Some feeds include source info
    source = getattr(entry, "source", None)
    if source:
        title = getattr(source, "title", None)
        if title:
            return title

    # Try to extract from title suffix like "Title - Source Name"
    title = entry.get("title", "")
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    if " | " in title:
        return title.rsplit(" | ", 1)[-1].strip()

    return ""

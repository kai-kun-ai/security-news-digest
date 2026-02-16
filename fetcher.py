"""RSSフィードの取得とパースを行うモジュール。"""

from datetime import UTC, datetime, timedelta
from typing import Any

import feedparser
from dateutil import parser as dateparser


def fetch_feeds(feeds_config: list[dict[str, str]], window_days: int = 3) -> list[dict[str, Any]]:
    """設定されたRSSフィードから指定期間内の記事を取得する。

    Parameters
    ----------
    feeds_config : list[dict[str, str]]
        フィード設定のリスト。各辞書は ``name``, ``url``, ``lang`` キーを持つ。
    window_days : int
        取得する過去日数。デフォルトは3日。

    Returns
    -------
    list[dict[str, Any]]
        取得した記事の辞書リスト。
    """
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
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


def _parse_date(entry: Any) -> datetime | None:
    """フィードエントリから公開日時をパースする。

    Parameters
    ----------
    entry : Any
        feedparserのエントリオブジェクト。

    Returns
    -------
    datetime or None
        パースされた日時。パースできない場合は ``None``。
    """
    for field in ("published", "updated", "created"):
        val = entry.get(field)
        if val:
            try:
                dt = dateparser.parse(val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt
            except (ValueError, TypeError):
                continue
    return None


def _extract_source(entry: Any) -> str:
    """フィードエントリから元のソース名を抽出する。

    Parameters
    ----------
    entry : Any
        feedparserのエントリオブジェクト。

    Returns
    -------
    str
        ソース名。抽出できない場合は空文字列。
    """
    source = getattr(entry, "source", None)
    if source:
        title = getattr(source, "title", None)
        if title:
            return title

    title = entry.get("title", "")
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    if " | " in title:
        return title.rsplit(" | ", 1)[-1].strip()

    return ""

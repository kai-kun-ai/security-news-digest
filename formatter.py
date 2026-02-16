"""要約済み記事をマークダウン形式に整形するモジュール。"""

from datetime import UTC, datetime
from typing import Any

CATEGORY_HEADERS = {
    "critical": "🔴 Critical / Actively Exploited",
    "notable": "⚠️ Notable",
    "jp": "🇯🇵 Japan / Japanese Sources",
    "general": "📰 General",
}

CATEGORY_ORDER = ["critical", "notable", "jp", "general"]


def format_digest(articles: list[dict[str, Any]], date_str: str | None = None) -> str:
    """記事リストをマークダウンダイジェストに整形する。

    Parameters
    ----------
    articles : list[dict[str, Any]]
        要約済み記事の辞書リスト。
    date_str : str or None
        ダイジェストの日付文字列。``None`` の場合はUTC現在日付を使用。

    Returns
    -------
    str
        マークダウン形式のダイジェスト文字列。
    """
    if date_str is None:
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")

    lines = [
        f"# Security News Digest — {date_str}",
        "",
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Articles: {len(articles)}",
        "",
        "---",
        "",
    ]

    by_cat: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORY_ORDER}
    for art in articles:
        cat = art.get("category", "general")
        if cat not in by_cat:
            cat = "general"
        by_cat[cat].append(art)

    for cat in CATEGORY_ORDER:
        items = by_cat[cat]
        if not items:
            continue

        lines.append(f"## {CATEGORY_HEADERS[cat]}")
        lines.append("")

        items.sort(key=lambda x: x.get("source_count", 1), reverse=True)

        for art in items:
            lines.append(f"### {art['title']}")
            lines.append("")
            if art.get("cves"):
                lines.append(f"**CVE:** {', '.join(art['cves'])}")
                lines.append("")
            lines.append(art.get("summary", ""))
            lines.append("")
            if art.get("sources"):
                lines.append(f"**Sources ({art.get('source_count', 1)}):** {', '.join(art['sources'])}")
            if art.get("urls"):
                for url in art["urls"][:3]:
                    lines.append(f"- <{url}>")
            lines.append("")
            lines.append("---")
            lines.append("")

    return "\n".join(lines)

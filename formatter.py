"""Format summarized articles into markdown output."""

from datetime import datetime, timezone
from typing import List, Dict, Any

CATEGORY_HEADERS = {
    "critical": "🔴 Critical / Actively Exploited",
    "notable": "⚠️ Notable",
    "jp": "🇯🇵 Japan / Japanese Sources",
    "general": "📰 General",
}

CATEGORY_ORDER = ["critical", "notable", "jp", "general"]


def format_digest(articles: List[Dict[str, Any]], date_str: str | None = None) -> str:
    """Format articles into a markdown digest."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        f"# Security News Digest — {date_str}",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Articles: {len(articles)}",
        "",
        "---",
        "",
    ]

    # Group by category
    by_cat: Dict[str, List[Dict[str, Any]]] = {c: [] for c in CATEGORY_ORDER}
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

        # Sort by source count descending
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

from formatter import format_digest


def test_format_digest_header():
    articles = []
    result = format_digest(articles, "2025-02-10")
    assert "# Security News Digest — 2025-02-10" in result
    assert "Articles: 0" in result


def test_format_digest_categories():
    articles = [
        {
            "title": "Critical Vuln",
            "summary": "A critical vulnerability.",
            "category": "critical",
            "sources": ["Source1"],
            "urls": ["https://example.com/1"],
            "cves": ["CVE-2025-0001"],
            "source_count": 2,
        },
        {
            "title": "General News",
            "summary": "Some news.",
            "category": "general",
            "sources": ["Source2"],
            "urls": ["https://example.com/2"],
            "cves": [],
            "source_count": 1,
        },
    ]
    result = format_digest(articles, "2025-02-10")
    assert "🔴 Critical / Actively Exploited" in result
    assert "📰 General" in result
    assert "CVE-2025-0001" in result
    assert "Critical Vuln" in result


def test_format_digest_skips_empty_categories():
    articles = [
        {
            "title": "JP News",
            "summary": "日本語ニュース",
            "category": "jp",
            "sources": [],
            "urls": [],
            "cves": [],
            "source_count": 1,
        },
    ]
    result = format_digest(articles, "2025-02-10")
    assert "🇯🇵 Japan" in result
    assert "🔴 Critical" not in result

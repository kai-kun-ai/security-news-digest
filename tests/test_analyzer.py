from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from analyzer import classify_gap_cause, find_gaps, parse_command


def test_find_gaps_url_match_and_title_similarity():
    reference = [
        {"title": "A", "url": "https://example.com/a"},
        {"title": "Critical RCE Exploit in Apache Server", "url": "https://example.com/b"},
        {"title": "C", "url": "https://example.com/c"},
    ]
    digest = [
        {"title": "Some title", "url": "https://example.com/a/"},
        {"title": "Critical RCE Exploit in Apache Server Found", "url": ""},
    ]

    gaps = find_gaps(reference, digest)
    assert [g["url"] for g in gaps] == ["https://example.com/c"]


def test_classify_gap_cause_feed_missing():
    gap = {"title": "Test", "url": "https://missed.example.net/post"}
    feeds = [{"name": "Example", "url": "https://example.com/rss", "lang": "en"}]
    out = classify_gap_cause(gap, feeds, [], [], {"window_days": 3})
    assert out["cause"] == "feed_missing"


def test_classify_gap_cause_outside_window_by_published_date():
    gap = {"title": "Old", "url": "https://example.com/old"}
    feeds = [{"name": "Example", "url": "https://example.com/rss", "lang": "en"}]
    old_dt = datetime.now(UTC) - timedelta(days=10)
    articles = [{"title": "Old", "url": "https://example.com/old", "published": old_dt}]
    out = classify_gap_cause(gap, feeds, articles, [], {"window_days": 1})
    assert out["cause"] == "outside_window"


def test_classify_gap_cause_dedup_merged_by_cve_overlap():
    gap = {"title": "CVE-2024-1234 exploited", "url": "https://example.com/x"}
    feeds = [{"name": "Example", "url": "https://example.com/rss", "lang": "en"}]
    groups = [[{"title": "Patch released for CVE-2024-1234", "summary": "", "url": "https://example.com/y"}]]
    out = classify_gap_cause(gap, feeds, [], groups, {"window_days": 3})
    assert out["cause"] == "dedup_merged"


def test_classify_gap_cause_interest_filtered():
    gap = {"title": "Linux kernel update", "url": "https://example.com/k"}
    feeds = [{"name": "Example", "url": "https://example.com/rss", "lang": "en"}]
    out = classify_gap_cause(gap, feeds, [], [], {"window_days": 3, "interest_keywords": ["windows"]})
    assert out["cause"] == "interest_filtered"


def test_classify_gap_cause_low_rank_when_fetched():
    gap = {"title": "Fetched but missing", "url": "https://example.com/z"}
    feeds = [{"name": "Example", "url": "https://example.com/rss", "lang": "en"}]
    articles = [{"title": "Fetched but missing", "url": "https://example.com/z", "published": datetime.now(UTC)}]
    out = classify_gap_cause(gap, feeds, articles, [], {"window_days": 3, "interest_keywords": []})
    assert out["cause"] == "low_rank"


@pytest.mark.parametrize(
    "line,expected",
    [
        ("list", ("list", [])),
        ("detail 3", ("detail", ["3"])),
        ("  SHOW-FIX 1  ", ("show-fix", ["1"])),
        ("", ("", [])),
    ],
)
def test_parse_command(line: str, expected: tuple[str, list[str]]):
    cmd = parse_command(line)
    assert (cmd.name, cmd.args) == expected

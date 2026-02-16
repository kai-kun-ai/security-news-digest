from types import SimpleNamespace

from fetcher import _extract_source, _parse_date


def test_parse_date_published():
    entry = {"published": "Mon, 10 Feb 2025 12:00:00 GMT"}
    result = _parse_date(entry)
    assert result is not None
    assert result.year == 2025
    assert result.tzinfo is not None


def test_parse_date_none():
    entry = {}
    assert _parse_date(entry) is None


def test_parse_date_invalid():
    entry = {"published": "not-a-date"}
    assert _parse_date(entry) is None


def test_extract_source_from_title_dash():
    entry = SimpleNamespace(**{"title": "Big Vuln - SecurityWeek"})
    entry.get = lambda k, d="": getattr(entry, k, d)
    result = _extract_source(entry)
    assert result == "SecurityWeek"


def test_extract_source_from_title_pipe():
    entry = SimpleNamespace(**{"title": "Big Vuln | The Hacker News"})
    entry.get = lambda k, d="": getattr(entry, k, d)
    result = _extract_source(entry)
    assert result == "The Hacker News"


def test_extract_source_empty():
    entry = SimpleNamespace(**{"title": "Simple Title"})
    entry.get = lambda k, d="": getattr(entry, k, d)
    result = _extract_source(entry)
    assert result == ""

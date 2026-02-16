from dedup import deduplicate, extract_cves, normalize_title, titles_similar


def test_extract_cves_found():
    text = "Patch for CVE-2024-1234 and CVE-2024-5678 released"
    result = extract_cves(text)
    assert result == {"CVE-2024-1234", "CVE-2024-5678"}


def test_extract_cves_empty():
    assert extract_cves("No CVEs here") == set()


def test_normalize_title_removes_suffix():
    assert normalize_title("Big Vuln - The Hacker News") == "big vuln"


def test_normalize_title_removes_bracket_prefix():
    assert normalize_title("[Breaking] Big Vuln") == "big vuln"


def test_titles_similar_true():
    assert titles_similar("critical vulnerability in linux kernel", "critical vulnerability in the linux kernel")


def test_titles_similar_false():
    assert not titles_similar("apple releases ios update", "google patches android flaw")


def test_deduplicate_by_url():
    articles = [
        {"title": "A", "url": "https://example.com/1", "summary": ""},
        {"title": "B", "url": "https://example.com/1", "summary": ""},
        {"title": "C", "url": "https://example.com/2", "summary": ""},
    ]
    groups = deduplicate(articles)
    assert len(groups) == 2
    assert len(groups[0]) == 2


def test_deduplicate_by_cve():
    articles = [
        {"title": "CVE-2024-1234 vuln", "url": "https://a.com", "summary": ""},
        {"title": "New flaw", "url": "https://b.com", "summary": "Details on CVE-2024-1234"},
    ]
    groups = deduplicate(articles)
    assert len(groups) == 1
    assert len(groups[0]) == 2


def test_deduplicate_by_title_similarity():
    articles = [
        {"title": "Critical Linux Kernel Vulnerability Found", "url": "https://a.com", "summary": ""},
        {"title": "Critical Linux Kernel Vulnerability Discovered", "url": "https://b.com", "summary": ""},
    ]
    groups = deduplicate(articles)
    assert len(groups) == 1

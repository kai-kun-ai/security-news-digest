"""Article deduplication logic."""

import re
from typing import List, Dict, Any
from difflib import SequenceMatcher

# Pattern for CVE IDs
CVE_PATTERN = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)

# Suffixes commonly appended by aggregators
SOURCE_SUFFIXES = [
    " - The Hacker News",
    " - BleepingComputer",
    " - SecurityWeek",
    " - Dark Reading",
    " - Krebs on Security",
    " - GBHackers on Security",
    " - Ars Technica",
    " - CISA",
    " | The Hacker News",
    " | BleepingComputer",
]


def extract_cves(text: str) -> set:
    """Extract all CVE IDs from text."""
    return set(CVE_PATTERN.findall(text.upper()))


def normalize_title(title: str) -> str:
    """Normalize a title for comparison."""
    t = title.strip()
    for suffix in SOURCE_SUFFIXES:
        if t.endswith(suffix):
            t = t[: -len(suffix)]
    # Remove bracketed prefixes like [Breaking]
    t = re.sub(r"^\[.*?\]\s*", "", t)
    return t.lower().strip()


def titles_similar(a: str, b: str, threshold: float = 0.75) -> bool:
    """Check if two normalized titles are similar enough."""
    return SequenceMatcher(None, a, b).ratio() >= threshold


def deduplicate(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Group duplicate articles together. Returns a list of article groups,
    where each group is a list of related articles (first is representative).
    """
    groups: List[List[Dict[str, Any]]] = []
    used = [False] * len(articles)

    for i, art in enumerate(articles):
        if used[i]:
            continue
        group = [art]
        used[i] = True

        url_i = art["url"]
        cves_i = extract_cves(art["title"] + " " + art.get("summary", ""))
        norm_i = normalize_title(art["title"])

        for j in range(i + 1, len(articles)):
            if used[j]:
                continue
            other = articles[j]

            # Same URL
            if url_i and url_i == other["url"]:
                group.append(other)
                used[j] = True
                continue

            # Shared CVE
            cves_j = extract_cves(other["title"] + " " + other.get("summary", ""))
            if cves_i and cves_j and cves_i & cves_j:
                group.append(other)
                used[j] = True
                continue

            # Similar title
            norm_j = normalize_title(other["title"])
            if titles_similar(norm_i, norm_j):
                group.append(other)
                used[j] = True
                continue

        groups.append(group)

    return groups

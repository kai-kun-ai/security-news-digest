#!/usr/bin/env python3
"""Security News Digest CLI - Fetch, deduplicate, summarize, and format security news."""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from fetcher import fetch_feeds
from dedup import deduplicate
from summarizer import summarize
from formatter import format_digest


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def rank_groups(groups, trusted_sources):
    """Sort article groups by relevance."""
    def score(group):
        s = len(group)  # More sources = higher
        for art in group:
            if art.get("source_name") in trusted_sources:
                s += 2
        return s

    groups.sort(key=score, reverse=True)
    return groups


def filter_by_interests(groups, keywords):
    """Filter article groups to only those matching interest keywords."""
    filtered = []
    kw_lower = [k.lower() for k in keywords]
    for group in groups:
        text = " ".join(
            (a["title"] + " " + a.get("summary", "")).lower() for a in group
        )
        if any(kw in text for kw in kw_lower):
            filtered.append(group)
    return filtered


def main():
    parser = argparse.ArgumentParser(
        description="Security News Digest - Fetch and summarize security news"
    )
    parser.add_argument(
        "--config", default="config.yaml", help="Path to config file"
    )
    parser.add_argument(
        "--interests", action="store_true",
        help="Filter articles by interest keywords defined in config"
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Skip LLM summarization (use heuristics only)"
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Override output directory"
    )
    args = parser.parse_args()

    config = load_config(args.config)

    # Fetch
    print("[*] Fetching feeds...")
    articles = fetch_feeds(config["feeds"], config.get("window_days", 3))
    print(f"    Fetched {len(articles)} articles")

    if not articles:
        print("[!] No articles found. Exiting.")
        sys.exit(0)

    # Deduplicate
    print("[*] Deduplicating...")
    groups = deduplicate(articles)
    print(f"    {len(groups)} unique article groups")

    # Rank
    trusted = set(config.get("trusted_sources", []))
    groups = rank_groups(groups, trusted)

    # Interest filtering
    if args.interests:
        keywords = config.get("interest_keywords", [])
        groups = filter_by_interests(groups, keywords)
        print(f"    {len(groups)} groups after interest filtering")

    # Summarize
    if args.no_llm:
        print("[*] Skipping LLM (heuristic mode)...")
        from summarizer import _guess_category
        results = []
        import dedup as dedup_mod
        for group in groups:
            rep = group[0]
            all_cves = set()
            all_sources = set()
            all_urls = []
            for a in group:
                all_cves |= dedup_mod.extract_cves(a["title"] + " " + a.get("summary", ""))
                if a.get("source_name"):
                    all_sources.add(a["source_name"])
                if a["url"]:
                    all_urls.append(a["url"])
            results.append({
                "title": rep["title"],
                "summary": rep.get("summary", ""),
                "category": _guess_category(group, rep),
                "sources": list(all_sources),
                "urls": list(set(all_urls)),
                "cves": list(all_cves),
                "source_count": len(group),
                "lang": rep.get("lang", "en"),
            })
    else:
        print("[*] Summarizing with LLM...")
        results = summarize(groups, config["llm"])

    # Format
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = format_digest(results, date_str)

    # Output
    out_dir = args.output_dir or config.get("output", {}).get("directory", "output")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    template = config.get("output", {}).get("filename_template", "digest_{date}.md")
    filename = template.replace("{date}", date_str)
    out_path = os.path.join(out_dir, filename)

    with open(out_path, "w") as f:
        f.write(digest)

    print(digest)
    print(f"\n[*] Digest written to {out_path}")


if __name__ == "__main__":
    main()

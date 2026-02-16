#!/usr/bin/env python3
"""セキュリティニュースダイジェストCLI。

RSSフィードの取得、重複排除、LLM要約、カテゴリ別マークダウン生成を行うツール。
"""

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from dedup import deduplicate
from fetcher import fetch_feeds
from formatter import format_digest
from summarizer import summarize


def load_feeds_file(path: str) -> list:
    """テキストファイルからフィードURLを読み込む。

    Parameters
    ----------
    path : str
        フィードURLが記載されたテキストファイルのパス。
        1行1URL、またはCSV形式（URL,lang,name）に対応。
        ``#`` で始まる行はコメントとして無視される。

    Returns
    -------
    list
        フィード設定の辞書リスト。各辞書は ``url``, ``lang``, ``name`` キーを持つ。
    """
    feeds = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            url = parts[0]
            lang = parts[1] if len(parts) > 1 else "en"
            name = parts[2] if len(parts) > 2 else url.split("/")[-1]
            feeds.append({"url": url, "lang": lang, "name": name})
    return feeds


def load_config(config_path: str = "config.yaml") -> dict:
    """YAML設定ファイルを読み込む。

    Parameters
    ----------
    config_path : str
        設定ファイルのパス。デフォルトは ``config.yaml``。

    Returns
    -------
    dict
        設定内容の辞書。
    """
    with open(config_path) as f:
        return yaml.safe_load(f)


def rank_groups(groups: list, trusted_sources: set) -> list:
    """記事グループを関連度でソートする。

    Parameters
    ----------
    groups : list
        記事グループのリスト。
    trusted_sources : set
        信頼ソース名のセット。

    Returns
    -------
    list
        ソート済みの記事グループリスト。
    """

    def score(group):
        s = len(group)
        for art in group:
            if art.get("source_name") in trusted_sources:
                s += 2
        return s

    groups.sort(key=score, reverse=True)
    return groups


def filter_by_interests(groups: list, keywords: list) -> list:
    """興味キーワードに一致する記事グループのみをフィルタリングする。

    Parameters
    ----------
    groups : list
        記事グループのリスト。
    keywords : list
        フィルタリング用のキーワードリスト。

    Returns
    -------
    list
        キーワードに一致したグループのリスト。
    """
    filtered = []
    kw_lower = [k.lower() for k in keywords]
    for group in groups:
        text = " ".join((a["title"] + " " + a.get("summary", "")).lower() for a in group)
        if any(kw in text for kw in kw_lower):
            filtered.append(group)
    return filtered


def main():
    """CLIエントリポイント。引数を解析し、ダイジェスト生成パイプラインを実行する。"""
    parser = argparse.ArgumentParser(description="Security News Digest - Fetch and summarize security news")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument(
        "--interests",
        action="store_true",
        help="Filter articles by interest keywords defined in config",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM summarization (use heuristics only)",
    )
    parser.add_argument("--output-dir", default=None, help="Override output directory")
    parser.add_argument(
        "--feeds-file",
        default=None,
        help="Path to a text file with feed URLs (one per line, format: URL or URL,lang,name)",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    if args.feeds_file:
        config["feeds"] = load_feeds_file(args.feeds_file)

    print("[*] Fetching feeds...")
    articles = fetch_feeds(config["feeds"], config.get("window_days", 3))
    print(f"    Fetched {len(articles)} articles")

    if not articles:
        print("[!] No articles found. Exiting.")
        sys.exit(0)

    print("[*] Deduplicating...")
    groups = deduplicate(articles)
    print(f"    {len(groups)} unique article groups")

    trusted = set(config.get("trusted_sources", []))
    groups = rank_groups(groups, trusted)

    if args.interests:
        keywords = config.get("interest_keywords", [])
        groups = filter_by_interests(groups, keywords)
        print(f"    {len(groups)} groups after interest filtering")

    if args.no_llm:
        print("[*] Skipping LLM (heuristic mode)...")
        import dedup as dedup_mod
        from summarizer import _guess_category

        results = []
        for group in groups:
            rep = group[0]
            all_cves: set = set()
            all_sources: set = set()
            all_urls: list = []
            for a in group:
                all_cves |= dedup_mod.extract_cves(a["title"] + " " + a.get("summary", ""))
                if a.get("source_name"):
                    all_sources.add(a["source_name"])
                if a["url"]:
                    all_urls.append(a["url"])
            results.append(
                {
                    "title": rep["title"],
                    "summary": rep.get("summary", ""),
                    "category": _guess_category(group, rep),
                    "sources": list(all_sources),
                    "urls": list(set(all_urls)),
                    "cves": list(all_cves),
                    "source_count": len(group),
                    "lang": rep.get("lang", "en"),
                }
            )
    else:
        print("[*] Summarizing with LLM...")
        results = summarize(groups, config["llm"])

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    digest = format_digest(results, date_str)

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

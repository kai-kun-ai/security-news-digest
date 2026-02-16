#!/usr/bin/env python3
"""セキュリティニュースダイジェストCLI。

RSSフィードの取得、重複排除、LLM要約、カテゴリ別マークダウン生成を行うツール。

Subcommands
-----------
- ``digest`` (default): generate a digest markdown
- ``analyze-gap``: compare our digest output against a third-party reference page
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from analyzer import (
    classify_gap_cause,
    fetch_reference,
    find_gaps,
    generate_suggestions,
    interactive_session,
    parse_digest_markdown,
)
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
        cfg = yaml.safe_load(f)
    if isinstance(cfg, dict):
        cfg["_config_path"] = config_path
    return cfg


def rank_groups(groups: list, trusted_sources: set) -> list:
    """記事グループを関連度でソートする。"""

    def score(group):
        s = len(group)
        for art in group:
            if art.get("source_name") in trusted_sources:
                s += 2
        return s

    groups.sort(key=score, reverse=True)
    return groups


def filter_by_interests(groups: list, keywords: list) -> list:
    """興味キーワードに一致する記事グループのみをフィルタリングする。"""
    filtered = []
    kw_lower = [k.lower() for k in keywords]
    for group in groups:
        text = " ".join((a["title"] + " " + a.get("summary", "")).lower() for a in group)
        if any(kw in text for kw in kw_lower):
            filtered.append(group)
    return filtered


def _write_digest(results: list[dict], config: dict, output_dir_override: str | None) -> str:
    """ダイジェストをファイルへ書き出し、出力パスを返す。"""
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    digest = format_digest(results, date_str)

    out_dir = output_dir_override or config.get("output", {}).get("directory", "output")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    template = config.get("output", {}).get("filename_template", "digest_{date}.md")
    filename = template.replace("{date}", date_str)
    out_path = os.path.join(out_dir, filename)

    with open(out_path, "w") as f:
        f.write(digest)

    print(digest)
    print(f"\n[*] Digest written to {out_path}")
    return out_path


def _latest_digest_file(config: dict) -> str | None:
    """output/ 内の最新ダイジェストMarkdownを返す。"""
    out_dir = config.get("output", {}).get("directory", "output")
    p = Path(out_dir)
    if not p.exists():
        return None
    candidates = sorted(p.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)
    return str(candidates[0]) if candidates else None


def run_digest(args: argparse.Namespace) -> int:
    """Digest サブコマンドの実行。"""
    config = load_config(args.config)

    if args.feeds_file:
        config["feeds"] = load_feeds_file(args.feeds_file)

    print("[*] Fetching feeds...")
    articles = fetch_feeds(config["feeds"], config.get("window_days", 3))
    print(f"    Fetched {len(articles)} articles")

    if not articles:
        print("[!] No articles found. Exiting.")
        return 0

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

    _write_digest(results, config, args.output_dir)
    return 0


def run_analyze_gap(args: argparse.Namespace) -> int:
    """analyze-gap サブコマンドの実行。"""
    config = load_config(args.config)

    print("[*] Fetching feeds (for analysis)...")
    articles = fetch_feeds(config["feeds"], config.get("window_days", 3))
    print(f"    Fetched {len(articles)} articles")

    print("[*] Deduplicating (for analysis)...")
    groups = deduplicate(articles)
    trusted = set(config.get("trusted_sources", []))
    groups = rank_groups(groups, trusted)

    digest_file = args.digest_file
    if digest_file is None:
        digest_file = _latest_digest_file(config)
    if digest_file is None:
        print("[!] digest file not found. Use --digest-file or generate a digest first.")
        return 2

    print(f"[*] Loading digest file: {digest_file}")
    digest_articles = parse_digest_markdown(digest_file)

    print(f"[*] Fetching reference URL: {args.reference_url}")
    reference_articles = fetch_reference(args.reference_url)
    print(f"    Extracted {len(reference_articles)} reference links")

    print("[*] Finding gaps...")
    gaps = find_gaps(reference_articles, digest_articles)
    print(f"    Gaps: {len(gaps)}")

    print("[*] Classifying gap causes...")
    for g in gaps:
        g["cause_info"] = classify_gap_cause(g, config.get("feeds", []), articles, groups, config)

    llm_cfg = {} if args.no_llm else config.get("llm", {})
    print("[*] Generating suggestions...")
    suggestions = generate_suggestions(gaps, config, llm_cfg)

    # Auto mode: print report and exit
    if args.auto:
        print(suggestions)
        return 0

    interactive_session(gaps, suggestions, config)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """argparseパーサを構築する。"""
    parser = argparse.ArgumentParser(description="Security News Digest - Fetch and summarize security news")
    subparsers = parser.add_subparsers(dest="command")

    # digest
    p_digest = subparsers.add_parser("digest", help="Generate digest markdown")
    p_digest.add_argument("--config", default="config.yaml", help="Path to config file")
    p_digest.add_argument(
        "--interests",
        action="store_true",
        help="Filter articles by interest keywords defined in config",
    )
    p_digest.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM summarization (use heuristics only)",
    )
    p_digest.add_argument("--output-dir", default=None, help="Override output directory")
    p_digest.add_argument(
        "--feeds-file",
        default=None,
        help="Path to a text file with feed URLs (one per line, format: URL or URL,lang,name)",
    )
    p_digest.set_defaults(func=run_digest)

    # analyze-gap
    p_an = subparsers.add_parser("analyze-gap", help="Analyze missed articles by comparing against a reference URL")
    p_an.add_argument("--reference-url", required=True, help="URL of the third-party blog/page to compare against")
    p_an.add_argument(
        "--digest-file",
        default=None,
        help="Path to our digest markdown to compare (default: latest in output/)",
    )
    p_an.add_argument("--config", default="config.yaml", help="Path to config file")
    p_an.add_argument("--no-llm", action="store_true", help="Skip LLM for suggestions")
    p_an.add_argument("--auto", action="store_true", help="Non-interactive mode (print report and exit)")
    p_an.set_defaults(func=run_analyze_gap)

    return parser


def main() -> None:
    """CLIエントリポイント。"""
    parser = build_parser()

    # Backward compatible default: if no subcommand is provided, run digest
    argv = sys.argv[1:]
    if argv and argv[0] in ("digest", "analyze-gap"):
        args = parser.parse_args(argv)
    else:
        args = parser.parse_args(["digest", *argv])

    if not hasattr(args, "func"):
        parser.print_help()
        raise SystemExit(2)

    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()

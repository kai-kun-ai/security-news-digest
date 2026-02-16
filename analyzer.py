"""ギャップ分析（第三者ソースとの比較）モジュール。

本モジュールは、第三者のブログ/ページに掲載されている記事リンク一覧と、
本ツールが生成したダイジェスト出力を比較し、収集漏れ（ギャップ）を検出する。
また、漏れの原因を推定し、改善提案（設定変更やコード変更の方向性）を生成する。

CLI からは ``analyze-gap`` サブコマンドで利用される。
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

import dedup


def fetch_reference(url: str) -> list[dict[str, str]]:
    """参照URL（第三者ページ）から記事タイトルとURLを抽出する。

    Parameters
    ----------
    url : str
        参照する第三者ページのURL。

    Returns
    -------
    list[dict[str, str]]
        抽出した記事のリスト。各要素は ``{"title": str, "url": str}``。

    Notes
    -----
    ページ構造はサイトごとに異なるため、厳密な抽出ではなく、HTML中の ``a[href]`` を
    基本として「テキスト（タイトル）」「リンクURL」を収集する。
    """
    resp = requests.get(url, timeout=20, headers={"User-Agent": "security-news-digest/1.0"})
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    items: list[dict[str, str]] = []

    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href")
        if not href:
            continue
        if not href.startswith("http://") and not href.startswith("https://"):
            continue

        title = " ".join(a.get_text(" ", strip=True).split())
        if not title:
            continue

        if href in seen:
            continue
        seen.add(href)
        items.append({"title": title, "url": href})

    return items


def _url_norm(u: str) -> str:
    """URLを比較用に正規化する。"""
    return u.strip().rstrip("/")


def find_gaps(reference_articles: list[dict[str, str]], digest_articles: list[dict[str, str]]) -> list[dict[str, Any]]:
    """参照記事とダイジェスト記事を比較し、未掲載（ギャップ）を抽出する。

    Parameters
    ----------
    reference_articles : list[dict[str, str]]
        第三者ページから抽出した記事リスト。
    digest_articles : list[dict[str, str]]
        自ツールのダイジェスト（出力）から抽出した記事リスト。

    Returns
    -------
    list[dict[str, Any]]
        ギャップ一覧。各要素は ``{"title": str, "url": str, "matched": bool}``。

    Notes
    -----
    一致判定は以下の順で行う。

    1) URLの完全一致（末尾/を除いた比較）
    2) タイトルの類似度（dedup.titles_similar + 正規化）
    """
    digest_urls = {_url_norm(a.get("url", "")) for a in digest_articles if a.get("url")}
    digest_titles_norm = [dedup.normalize_title(a.get("title", "")) for a in digest_articles]

    gaps: list[dict[str, Any]] = []
    for ref in reference_articles:
        ref_url = _url_norm(ref.get("url", ""))
        ref_title = ref.get("title", "")

        matched = False
        if ref_url and ref_url in digest_urls:
            matched = True
        else:
            ref_norm = dedup.normalize_title(ref_title)
            for dt in digest_titles_norm:
                if dt and ref_norm and dedup.titles_similar(ref_norm, dt):
                    matched = True
                    break

        if not matched:
            gaps.append({"title": ref_title, "url": ref.get("url", ""), "matched": False})

    return gaps


def _domains_from_feeds(feeds_config: list[dict[str, str]]) -> set[str]:
    """feeds設定からドメイン集合を抽出する。"""
    domains: set[str] = set()
    for f in feeds_config or []:
        u = f.get("url", "")
        if not u:
            continue
        try:
            domains.add(urlparse(u).netloc.lower())
        except Exception:
            continue
    return {d for d in domains if d}


def _extract_domain(url: str) -> str:
    """URLからドメインを抽出する。"""
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _parse_interest_keywords(config: dict) -> list[str]:
    """設定から興味キーワードを取得する。"""
    kws = config.get("interest_keywords", []) if isinstance(config, dict) else []
    if not isinstance(kws, list):
        return []
    return [str(k) for k in kws if str(k).strip()]


def _matches_interest(text: str, keywords: list[str]) -> bool:
    """テキストが興味キーワードに一致するかを判定する。"""
    t = text.lower()
    return any(k.lower() in t for k in keywords)


def classify_gap_cause(
    gap: dict[str, Any],
    feeds_config: list[dict[str, str]],
    articles_fetched: list[dict[str, Any]],
    groups_deduped: list[list[dict[str, Any]]],
    config: dict[str, Any],
) -> dict[str, str]:
    """ギャップ（未掲載記事）の原因を推定する。

    Parameters
    ----------
    gap : dict
        ギャップ情報（``title``/``url`` を含む）。
    feeds_config : list[dict[str, str]]
        設定されたフィード一覧。
    articles_fetched : list[dict[str, Any]]
        フィードから取得した記事一覧（fetcher.fetch_feeds の出力）。
    groups_deduped : list[list[dict[str, Any]]]
        dedup.deduplicate により生成された重複排除後グループ。
    config : dict[str, Any]
        全体設定。

    Returns
    -------
    dict[str, str]
        ``{"cause": str, "detail": str, "suggestion": str}``。

    Notes
    -----
    厳密な因果推定は不可能なため、複数のヒューリスティックを用いて
    最も可能性の高い原因を1つ選ぶ。
    """
    gap_url = str(gap.get("url", ""))
    gap_title = str(gap.get("title", ""))
    gap_domain = _extract_domain(gap_url)

    feed_domains = _domains_from_feeds(feeds_config)
    window_days = int(config.get("window_days", 3) or 3)
    cutoff = datetime.now(UTC) - timedelta(days=window_days)

    # 1) feed_missing
    if gap_domain and gap_domain not in feed_domains:
        return {
            "cause": "feed_missing",
            "detail": f"参照記事のドメイン({gap_domain})が設定されたRSSフィード群に含まれていない可能性が高い。",
            "suggestion": (
                "config.yamlのfeedsに該当ソースのRSSを追加する。例:\n"
                "feeds:\n"
                f"  - name: {gap_domain}\n"
                f"    url: https://{gap_domain}/feed\n"
                "    lang: en\n"
            ),
        }

    # 2) outside_window（取得済み記事に存在するが期間外の公開日）
    for art in articles_fetched or []:
        if gap_url and _url_norm(art.get("url", "")) == _url_norm(gap_url):
            published = art.get("published")
            if published and published < cutoff:
                return {
                    "cause": "outside_window",
                    "detail": (
                        f"同一URLの記事が存在するが、公開日({published.isoformat()})が時間窓(window_days={window_days})の外。"
                    ),
                    "suggestion": "config.yamlのwindow_daysを拡大する（例: 3→7）。",
                }

    # 3) dedup_merged（同一CVEなどで別記事に吸収されている可能性）
    gap_cves = dedup.extract_cves(gap_title)
    if gap_cves:
        for group in groups_deduped or []:
            group_cves: set[str] = set()
            for a in group:
                group_cves |= dedup.extract_cves(a.get("title", "") + " " + a.get("summary", ""))
            if group_cves and (gap_cves & group_cves):
                rep = group[0]
                return {
                    "cause": "dedup_merged",
                    "detail": (
                        f"CVEが一致するため、別記事グループ（代表: {rep.get('title', '')[:80]}）"
                        "へ統合されている可能性。"
                    ),
                    "suggestion": "重複排除の類似度閾値（dedup.titles_similar）やCVE統合ルールを見直す。",
                }

    # 4) interest_filtered
    keywords = _parse_interest_keywords(config)
    if keywords and not _matches_interest(gap_title, keywords):
        return {
            "cause": "interest_filtered",
            "detail": "興味キーワード（interest_keywords）に一致しないため、フィルタリング条件で落ちた可能性。",
            "suggestion": "config.yamlのinterest_keywordsに必要なキーワードを追加する。",
        }

    # 5) low_rank（取得はできているが最終出力に含まれない）
    for art in articles_fetched or []:
        if gap_url and _url_norm(art.get("url", "")) == _url_norm(gap_url):
            return {
                "cause": "low_rank",
                "detail": "記事は取得できているが、グルーピング/ランク付け/要約後の出力に反映されていない可能性。",
                "suggestion": "trusted_sourcesの追加やランク付けロジックの調整を検討する。",
            }

    return {
        "cause": "unknown",
        "detail": "利用可能な情報から原因を特定できない。",
        "suggestion": "参照ページと取得済み記事の突き合わせ精度（URL正規化/タイトル類似度）を改善する。",
    }


def _llm_call(primary_cfg: dict[str, Any], fallback_cfg: dict[str, Any], system: str, user: str) -> str | None:
    """summarizer.pyと同様のプライマリ/フォールバックでLLMを呼び出す。"""
    try:
        from openai import OpenAI
    except Exception:
        return None

    def call(cfg: dict[str, Any]) -> str | None:
        import os

        api_key = os.environ.get(cfg.get("api_key_env", ""), "")
        if not api_key:
            return None
        client = OpenAI(base_url=cfg["api_base"], api_key=api_key)
        try:
            resp = client.chat.completions.create(
                model=cfg["model"],
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=cfg.get("max_tokens", 1024),
                temperature=cfg.get("temperature", 0.2),
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            return None

    out = call(primary_cfg)
    if out is None:
        out = call(fallback_cfg)
    return out


def generate_suggestions(
    gaps_with_causes: list[dict[str, Any]],
    config: dict[str, Any],
    llm_config: dict[str, Any],
) -> str:
    """ギャップ分析結果から改善提案レポートを生成する。

    Parameters
    ----------
    gaps_with_causes : list[dict[str, Any]]
        ``gap`` に ``cause_info`` を付与したリスト。
    config : dict[str, Any]
        設定（config.yaml相当）。
    llm_config : dict[str, Any]
        LLM設定（summarizerと同型: primary/fallback）。

    Returns
    -------
    str
        日本語の改善提案レポート。

    Notes
    -----
    LLMが利用不可の場合は、原因分類結果から簡易レポートを生成する。
    """
    # ヒューリスティックレポート（常に生成し、LLMが使える場合は上書き）
    by_cause: dict[str, list[dict[str, Any]]] = {}
    for g in gaps_with_causes:
        c = (g.get("cause_info") or {}).get("cause", "unknown")
        by_cause.setdefault(c, []).append(g)

    lines = ["## 分析サマリー", "", f"検出ギャップ数: {len(gaps_with_causes)}", "", "## 改善提案", ""]
    for cause, items in sorted(by_cause.items(), key=lambda x: (-len(x[1]), x[0])):
        lines.append(f"### {cause} ({len(items)})")
        for it in items[:10]:
            title = it.get("title", "")
            sug = (it.get("cause_info") or {}).get("suggestion", "")
            lines.append(f"- [ ] {title} — {sug}")
        if len(items) > 10:
            lines.append(f"- ... ({len(items) - 10} more)")
        lines.append("")

    heuristic_report = "\n".join(lines).strip() + "\n"

    if not llm_config:
        return heuristic_report

    system_prompt = (
        "You are a security news feed optimization assistant. "
        "Given gaps (articles a reference source covered but we missed) and pre-classified causes, "
        "suggest specific improvements."
    )
    # ユーザープロンプトは日本語出力を強制し、exact change を要求
    gap_block = []
    for i, g in enumerate(gaps_with_causes, start=1):
        ci = g.get("cause_info") or {}
        gap_block.append(
            f"[{i}] Title: {g.get('title', '')}\n"
            f"URL: {g.get('url', '')}\n"
            f"Cause: {ci.get('cause', 'unknown')}\n"
            f"Detail: {ci.get('detail', '')}\n"
        )

    user_prompt = (
        "Given the following gaps (articles a reference source covered but we missed), analyze the root causes "
        "and suggest specific improvements.\n\n"
        "For each gap, the cause has been pre-classified. Your job is to:\n"
        "1. Summarize the gaps in Japanese\n"
        "2. Group improvement suggestions by category\n"
        "3. For EACH suggestion, provide the EXACT change needed (e.g., config.yaml change snippet)\n"
        "4. Prioritize by impact (how many gaps each fix would address)\n\n"
        "Output format:\n"
        "## 分析サマリー\n...\n"
        "## 改善提案\n"
        "### 1. フィード追加\n- [ ] ...\n"
        "### 2. キーワード追加\n- [ ] ...\n"
        "### 3. 設定調整\n- [ ] ...\n\n"
        "GAPS:\n" + "\n---\n".join(gap_block)
    )

    primary_cfg = {
        **llm_config.get("primary", {}),
        "max_tokens": llm_config.get("max_tokens", 1024),
        "temperature": llm_config.get("temperature", 0.2),
    }
    fallback_cfg = {
        **llm_config.get("fallback", {}),
        "max_tokens": llm_config.get("max_tokens", 1024),
        "temperature": llm_config.get("temperature", 0.2),
    }

    llm_text = _llm_call(primary_cfg, fallback_cfg, system_prompt, user_prompt)
    if llm_text is None:
        return heuristic_report
    return llm_text.strip() + "\n"


@dataclass
class ParsedCommand:
    """対話モードのコマンド解析結果。"""

    name: str
    args: list[str]


def parse_command(line: str) -> ParsedCommand:
    """対話セッション入力をコマンドに分解する。

    Parameters
    ----------
    line : str
        入力行。

    Returns
    -------
    ParsedCommand
        コマンド名と引数配列。
    """
    raw = (line or "").strip()
    if not raw:
        return ParsedCommand(name="", args=[])
    parts = raw.split()
    return ParsedCommand(name=parts[0].lower(), args=parts[1:])


def _yaml_dump(obj: Any) -> str:
    """YAML文字列としてダンプする（PyYAMLがある前提）。"""
    import yaml

    return yaml.safe_dump(obj, sort_keys=False, allow_unicode=True)


def _apply_fix_to_config(config_path: str, new_config: dict[str, Any]) -> str:
    """config.yamlを更新し、差分（unified diff）を返す。"""
    p = Path(config_path)
    before = p.read_text(encoding="utf-8") if p.exists() else ""
    after = _yaml_dump(new_config)

    if p.exists():
        p.write_text(after, encoding="utf-8")
    else:
        p.write_text(after, encoding="utf-8")

    diff = "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=str(p),
            tofile=str(p),
            lineterm="",
        )
    )
    return diff


def interactive_session(gaps: list[dict[str, Any]], suggestions: str, config: dict[str, Any]) -> None:
    """対話形式でギャップ/提案を閲覧・適用する。

    Parameters
    ----------
    gaps : list[dict[str, Any]]
        ギャップ一覧（各要素に ``cause_info`` が付与されている想定）。
    suggestions : str
        提案レポート（日本語）。
    config : dict[str, Any]
        現在の設定（読み込み済み）。

    Notes
    -----
    プロンプトは英語、説明は日本語で表示する。
    ``apply`` は安全のため確認を必須とし、適用できる変更のみ（例: window_days, interest_keywords, feedsの追加）を扱う。
    """

    def print_help() -> None:
        print(
            "Commands: list | detail <n> | suggest | show-fix <n> | apply <n> | help | quit/q\n"
            "説明: listで漏れ一覧、detailで原因、suggestで全体提案、applyで一部の設定変更を試行します。"
        )

    print("Entering interactive gap analysis session.")
    print_help()

    config_path = str(config.get("_config_path", "config.yaml"))

    while True:
        try:
            line = input("analyze-gap> ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return

        cmd = parse_command(line)
        if cmd.name in ("quit", "q", "exit"):
            print("Bye.")
            return

        if cmd.name in ("help", "h", "?"):
            print_help()
            continue

        if cmd.name == "list":
            if not gaps:
                print("No gaps.")
                continue
            for i, g in enumerate(gaps, start=1):
                ci = g.get("cause_info") or {}
                print(f"[{i}] {g.get('title', '')} ({ci.get('cause', 'unknown')})")
            continue

        if cmd.name == "detail":
            if not cmd.args:
                print("Usage: detail <n>")
                continue
            try:
                n = int(cmd.args[0])
            except ValueError:
                print("n must be an integer")
                continue
            if n < 1 or n > len(gaps):
                print("out of range")
                continue
            g = gaps[n - 1]
            ci = g.get("cause_info") or {}
            print(f"Title: {g.get('title', '')}")
            print(f"URL: {g.get('url', '')}")
            print(f"Cause: {ci.get('cause', 'unknown')}")
            print(f"Detail: {ci.get('detail', '')}")
            continue

        if cmd.name == "suggest":
            print(suggestions)
            continue

        if cmd.name == "show-fix":
            if not cmd.args:
                print("Usage: show-fix <n>")
                continue
            try:
                n = int(cmd.args[0])
            except ValueError:
                print("n must be an integer")
                continue
            if n < 1 or n > len(gaps):
                print("out of range")
                continue
            ci = gaps[n - 1].get("cause_info") or {}
            print(ci.get("suggestion", "(no suggestion)"))
            continue

        if cmd.name == "apply":
            if not cmd.args:
                print("Usage: apply <n>")
                continue
            try:
                n = int(cmd.args[0])
            except ValueError:
                print("n must be an integer")
                continue
            if n < 1 or n > len(gaps):
                print("out of range")
                continue

            g = gaps[n - 1]
            ci = g.get("cause_info") or {}
            cause = ci.get("cause", "unknown")

            # 変更案を作成
            new_config = dict(config)
            if cause == "outside_window":
                cur = int(new_config.get("window_days", 3) or 3)
                new_config["window_days"] = max(cur, 7)
                action_desc = f"Set window_days: {cur} -> {new_config['window_days']}"
            elif cause == "interest_filtered":
                kws = list(_parse_interest_keywords(new_config))
                print("Enter a keyword to add (English prompt / 日本語説明: interest_keywordsへ追加する語を入力):")
                kw = input("keyword> ").strip()
                if not kw:
                    print("Canceled (empty keyword).")
                    continue
                if kw not in kws:
                    kws.append(kw)
                new_config["interest_keywords"] = kws
                action_desc = f"Add interest keyword: {kw}"
            elif cause == "feed_missing":
                dom = _extract_domain(str(g.get("url", "")))
                feeds = list(new_config.get("feeds", []) or [])
                feeds.append({"name": dom or "new-source", "url": f"https://{dom}/feed" if dom else "", "lang": "en"})
                new_config["feeds"] = feeds
                action_desc = f"Append feed placeholder for domain: {dom}"
            else:
                print("This fix cannot be applied automatically. (自動適用できません)")
                continue

            print(f"About to apply change: {action_desc}")
            confirm = input("Proceed? [y/N] ").strip().lower()
            if confirm not in ("y", "yes"):
                print("Canceled.")
                continue

            diff = _apply_fix_to_config(config_path, new_config)
            print("Applied. Diff:")
            print(diff or "(no diff)")
            # config更新
            config.update(new_config)
            continue

        if cmd.name:
            print("Unknown command. Type 'help'.")
            continue


def parse_digest_markdown(path: str) -> list[dict[str, str]]:
    """ダイジェストMarkdownから記事タイトルとURLを抽出する。

    Parameters
    ----------
    path : str
        ダイジェストMarkdownのパス。

    Returns
    -------
    list[dict[str, str]]
        ``{"title": str, "url": str}`` のリスト。

    Notes
    -----
    formatter.format_digest の出力形式に合わせて以下を抽出する。

    - 見出し ``### Title`` をタイトルとして取得
    - 直後の ``- <https://...>`` 行をURLとして取得

    1つのタイトルに複数URLがある場合はURLごとにレコードを作る。
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    cur_title: str | None = None
    out: list[dict[str, str]] = []

    url_re = re.compile(r"^-\s*<(?P<url>https?://[^>]+)>")

    for line in text.splitlines():
        if line.startswith("### "):
            cur_title = line[4:].strip()
            continue
        m = url_re.match(line.strip())
        if m and cur_title:
            out.append({"title": cur_title, "url": m.group("url")})

    # タイトルはあるがURLが無い記事も念のため保持
    if not out:
        # fallback: plain links
        link_re = re.compile(r"<(?P<url>https?://[^>]+)>")
        for m in link_re.finditer(text):
            out.append({"title": m.group("url"), "url": m.group("url")})

    return out

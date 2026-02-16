"""記事の重複排除ロジックを提供するモジュール。"""

import re
from difflib import SequenceMatcher
from typing import Any

CVE_PATTERN = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)

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
    """テキストからすべてのCVE IDを抽出する。

    Parameters
    ----------
    text : str
        CVE IDを検索する対象テキスト。

    Returns
    -------
    set
        抽出されたCVE IDの文字列セット。
    """
    return set(CVE_PATTERN.findall(text.upper()))


def normalize_title(title: str) -> str:
    """タイトルを正規化して比較可能にする。

    Parameters
    ----------
    title : str
        正規化する記事タイトル。

    Returns
    -------
    str
        小文字化・サフィックス除去・プレフィックス除去された正規化タイトル。
    """
    t = title.strip()
    for suffix in SOURCE_SUFFIXES:
        if t.endswith(suffix):
            t = t[: -len(suffix)]
    t = re.sub(r"^\[.*?\]\s*", "", t)
    return t.lower().strip()


def titles_similar(a: str, b: str, threshold: float = 0.75) -> bool:
    """2つの正規化タイトルの類似度を判定する。

    Parameters
    ----------
    a : str
        比較元の正規化タイトル。
    b : str
        比較先の正規化タイトル。
    threshold : float
        類似度の閾値。デフォルトは0.75。

    Returns
    -------
    bool
        類似度が閾値以上の場合 ``True``。
    """
    return SequenceMatcher(None, a, b).ratio() >= threshold


def deduplicate(articles: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """重複記事をグルーピングする。

    URL一致、共通CVE、タイトル類似度の3つの基準で記事をグループ化する。
    各グループの先頭が代表記事となる。

    Parameters
    ----------
    articles : list[dict[str, Any]]
        記事の辞書リスト。

    Returns
    -------
    list[list[dict[str, Any]]]
        グループ化された記事リストのリスト。
    """
    groups: list[list[dict[str, Any]]] = []
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

            if url_i and url_i == other["url"]:
                group.append(other)
                used[j] = True
                continue

            cves_j = extract_cves(other["title"] + " " + other.get("summary", ""))
            if cves_i and cves_j and cves_i & cves_j:
                group.append(other)
                used[j] = True
                continue

            norm_j = normalize_title(other["title"])
            if titles_similar(norm_i, norm_j):
                group.append(other)
                used[j] = True
                continue

        groups.append(group)

    return groups

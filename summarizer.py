"""LLM-based summarization and categorization with fallback."""

import os
import json
from typing import List, Dict, Any, Optional
from openai import OpenAI

SYSTEM_PROMPT = """\
You are a cybersecurity news analyst. Your task is to analyze article groups and produce a JSON response.

For each article group, provide:
1. "summary" — A concise summary in Japanese (2-3 sentences). Include CVE IDs and CVSS scores if mentioned.
2. "category" — One of: "critical" (CVSS>=9.0, KEV, actively exploited), "notable", "jp" (Japanese-language news), "general"
3. "title" — A short descriptive title in Japanese

Be concise and accurate. Always include CVE IDs when present.
Respond with valid JSON only: {"articles": [{"title": "...", "summary": "...", "category": "..."}]}
"""


def _build_prompt(groups: List[List[Dict[str, Any]]]) -> str:
    """Build the user prompt from article groups."""
    parts = []
    for i, group in enumerate(groups):
        rep = group[0]
        sources = ", ".join(set(a.get("source_name", "") for a in group if a.get("source_name")))
        cve_text = ", ".join(set(
            cve for a in group
            for cve in __import__("dedup").extract_cves(a["title"] + " " + a.get("summary", ""))
        ))
        parts.append(
            f"[Article {i+1}]\n"
            f"Title: {rep['title']}\n"
            f"Sources ({len(group)}): {sources or 'unknown'}\n"
            f"CVEs: {cve_text or 'none'}\n"
            f"Language: {rep.get('lang', 'en')}\n"
            f"Summary: {rep.get('summary', 'N/A')[:500]}\n"
        )
    return "\n---\n".join(parts)


def _call_llm(config: dict, groups: List[List[Dict[str, Any]]]) -> Optional[dict]:
    """Try calling the LLM with the given config."""
    api_key = os.environ.get(config["api_key_env"], "")
    if not api_key:
        return None

    client = OpenAI(base_url=config["api_base"], api_key=api_key)
    user_prompt = _build_prompt(groups)

    try:
        response = client.chat.completions.create(
            model=config["model"],
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=config.get("max_tokens", 1024),
            temperature=config.get("temperature", 0.3),
        )
        content = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[:-3]
        return json.loads(content)
    except Exception as e:
        print(f"[WARN] LLM call failed ({config['model']}): {e}")
        return None


def summarize(groups: List[List[Dict[str, Any]]], llm_config: dict) -> List[Dict[str, Any]]:
    """
    Summarize and categorize article groups using LLM.
    Returns list of dicts with title, summary, category, sources, urls, cves.
    Falls back to basic extraction if LLM unavailable.
    """
    import dedup

    # Try primary, then fallback
    primary_cfg = {**llm_config["primary"], "max_tokens": llm_config.get("max_tokens", 1024),
                   "temperature": llm_config.get("temperature", 0.3)}
    fallback_cfg = {**llm_config["fallback"], "max_tokens": llm_config.get("max_tokens", 1024),
                    "temperature": llm_config.get("temperature", 0.3)}

    llm_result = _call_llm(primary_cfg, groups)
    if llm_result is None:
        print("[INFO] Primary LLM unavailable, trying fallback...")
        llm_result = _call_llm(fallback_cfg, groups)

    results = []
    for i, group in enumerate(groups):
        rep = group[0]
        all_cves = set()
        all_sources = set()
        all_urls = []
        for a in group:
            all_cves |= dedup.extract_cves(a["title"] + " " + a.get("summary", ""))
            if a.get("source_name"):
                all_sources.add(a["source_name"])
            if a["url"]:
                all_urls.append(a["url"])

        entry = {
            "title": rep["title"],
            "summary": rep.get("summary", ""),
            "category": _guess_category(group, rep),
            "sources": list(all_sources),
            "urls": list(set(all_urls)),
            "cves": list(all_cves),
            "source_count": len(group),
            "lang": rep.get("lang", "en"),
        }

        # Overlay LLM results if available
        if llm_result and "articles" in llm_result and i < len(llm_result["articles"]):
            llm_art = llm_result["articles"][i]
            entry["title"] = llm_art.get("title", entry["title"])
            entry["summary"] = llm_art.get("summary", entry["summary"])
            entry["category"] = llm_art.get("category", entry["category"])

        results.append(entry)

    return results


def _guess_category(group: List[Dict[str, Any]], rep: Dict[str, Any]) -> str:
    """Heuristic category when LLM is unavailable."""
    text = (rep["title"] + " " + rep.get("summary", "")).lower()

    if rep.get("lang") == "ja":
        return "jp"

    # Check for critical indicators
    critical_terms = ["actively exploited", "kev", "cvss 9", "cvss 10", "critical vulnerability",
                      "zero-day", "0-day", "in the wild"]
    if any(term in text for term in critical_terms):
        return "critical"

    # CVSS score check
    import re
    cvss_match = re.search(r"cvss[:\s]*(\d+\.?\d*)", text)
    if cvss_match and float(cvss_match.group(1)) >= 9.0:
        return "critical"

    if len(group) >= 3:
        return "notable"

    return "general"

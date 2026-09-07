"""Share of voice and run summaries."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Mapping, Optional


def share_of_voice(rows: Iterable[Mapping]) -> Dict[str, Dict[str, float]]:
    """Per brand: mention_rate, citation_rate, share_of_voice.

    `rows` are detection rows with keys brand, mentioned, cited (0/1).
    share_of_voice = brand mentions / total mentions across all brands (0 if none).
    """
    mentions: Dict[str, int] = defaultdict(int)
    cites: Dict[str, int] = defaultdict(int)
    prompts: Dict[str, int] = defaultdict(int)
    for r in rows:
        b = r["brand"]
        prompts[b] += 1
        mentions[b] += int(r["mentioned"])
        cites[b] += int(r["cited"])
    total_mentions = sum(mentions.values())
    out: Dict[str, Dict[str, float]] = {}
    for b in prompts:
        n = prompts[b] or 1
        out[b] = {
            "prompts": prompts[b],
            "mentions": mentions[b],
            "citations": cites[b],
            "mention_rate": round(mentions[b] / n, 4),
            "citation_rate": round(cites[b] / n, 4),
            "share_of_voice": round(mentions[b] / total_mentions, 4) if total_mentions else 0.0,
        }
    return out


def by_provider(rows: Iterable[Mapping]) -> Dict[str, Dict[str, Dict[str, float]]]:
    groups: Dict[str, List[Mapping]] = defaultdict(list)
    for r in rows:
        groups[r["provider"]].append(r)
    return {p: share_of_voice(rs) for p, rs in groups.items()}


def summarize_run(rows: Iterable[Mapping], previous_rows: Optional[Iterable[Mapping]] = None) -> dict:
    rows = list(rows)
    summary = {
        "overall": share_of_voice(rows),
        "by_provider": by_provider(rows),
        "gaps": gaps(rows),
    }
    if previous_rows is not None:
        prev = share_of_voice(list(previous_rows))
        summary["delta"] = {
            b: {
                "mention_rate": round(cur["mention_rate"] - prev.get(b, {}).get("mention_rate", 0.0), 4),
                "citation_rate": round(cur["citation_rate"] - prev.get(b, {}).get("citation_rate", 0.0), 4),
                "share_of_voice": round(cur["share_of_voice"] - prev.get(b, {}).get("share_of_voice", 0.0), 4),
            }
            for b, cur in summary["overall"].items()
        }
    return summary


def gaps(rows: Iterable[Mapping], primary: Optional[str] = None) -> List[dict]:
    """Prompts where the primary brand (first brand seen) is absent but a competitor appears.

    These are the highest-value GEO opportunities: the engine already answers
    the question with a brand, just not yours.
    """
    rows = list(rows)
    if not rows:
        return []
    primary = primary or rows[0]["brand"]
    per_prompt: Dict[tuple, Dict[str, Mapping]] = defaultdict(dict)
    for r in rows:
        per_prompt[(r["provider"], r["prompt"])][r["brand"]] = r
    out = []
    for (provider, prompt), brands in per_prompt.items():
        me = brands.get(primary)
        if me is None or me["mentioned"]:
            continue
        rivals = [b for b, r in brands.items() if b != primary and r["mentioned"]]
        if rivals:
            out.append({"provider": provider, "prompt": prompt, "competitors_mentioned": rivals})
    return out

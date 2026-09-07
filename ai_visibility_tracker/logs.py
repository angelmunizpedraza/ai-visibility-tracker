"""AI-crawler analysis from web server access logs (Nginx/Apache combined format).

Answers a question most SEO teams cannot answer today: *are AI engines actually
crawling my site, which pages, and how often?* Being cited by ChatGPT or
Perplexity requires being crawled by their bots first.
"""

from __future__ import annotations

import gzip
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

# Known AI crawlers / fetchers and the company behind them.
AI_BOTS: Dict[str, str] = {
    "GPTBot": "OpenAI (training)",
    "ChatGPT-User": "OpenAI (browsing on behalf of a user)",
    "OAI-SearchBot": "OpenAI (search index)",
    "ClaudeBot": "Anthropic (training)",
    "Claude-User": "Anthropic (browsing on behalf of a user)",
    "Claude-SearchBot": "Anthropic (search index)",
    "anthropic-ai": "Anthropic (legacy)",
    "PerplexityBot": "Perplexity (index)",
    "Perplexity-User": "Perplexity (browsing on behalf of a user)",
    "Google-Extended": "Google (Gemini training opt-out token)",
    "GoogleOther": "Google (other, incl. AI products)",
    "Applebot-Extended": "Apple (AI training)",
    "Amazonbot": "Amazon (Alexa/AI)",
    "Bytespider": "ByteDance",
    "CCBot": "Common Crawl (used for LLM training)",
    "meta-externalagent": "Meta (AI training)",
    "FacebookBot": "Meta",
    "cohere-ai": "Cohere",
    "DuckAssistBot": "DuckDuckGo AI",
    "YouBot": "You.com",
    "MistralAI-User": "Mistral",
}

# Combined Log Format: ip - - [time] "METHOD path HTTP/x" status bytes "referer" "ua"
LINE_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+) [^"]*" '
    r'(?P<status>\d{3}) (?P<bytes>\S+) "(?P<referer>[^"]*)" "(?P<ua>[^"]*)"'
)


@dataclass
class BotStats:
    bot: str
    vendor: str
    hits: int = 0
    statuses: Counter = field(default_factory=Counter)
    paths: Counter = field(default_factory=Counter)
    days: Counter = field(default_factory=Counter)

    @property
    def blocked_rate(self) -> float:
        blocked = sum(v for k, v in self.statuses.items() if k in ("401", "403", "429"))
        return round(blocked / self.hits, 4) if self.hits else 0.0


def identify_bot(user_agent: str) -> Optional[str]:
    ua = user_agent or ""
    for bot in AI_BOTS:
        if bot.lower() in ua.lower():
            return bot
    return None


def iter_lines(path: str | Path) -> Iterator[str]:
    p = Path(path)
    opener = gzip.open if p.suffix == ".gz" else open
    with opener(p, "rt", encoding="utf-8", errors="replace") as fh:  # type: ignore[arg-type]
        for line in fh:
            yield line.rstrip("\n")


def parse_line(line: str) -> Optional[dict]:
    m = LINE_RE.match(line)
    if not m:
        return None
    d = m.groupdict()
    # "10/Sep/2026:08:14:22 +0000" -> "2026-09-10"
    try:
        day, mon, rest = d["time"].split("/", 2)
        year = rest.split(":")[0]
        d["day"] = f"{year}-{mon}-{day}"
    except ValueError:
        d["day"] = d["time"][:11]
    return d


def analyse(lines: Iterable[str], top_paths: int = 10) -> Dict[str, BotStats]:
    stats: Dict[str, BotStats] = {}
    for line in lines:
        rec = parse_line(line)
        if not rec:
            continue
        bot = identify_bot(rec["ua"])
        if not bot:
            continue
        s = stats.setdefault(bot, BotStats(bot, AI_BOTS[bot]))
        s.hits += 1
        s.statuses[rec["status"]] += 1
        s.paths[rec["path"]] += 1
        s.days[rec["day"]] += 1
    return stats


def to_report(stats: Dict[str, BotStats], top_paths: int = 10) -> List[dict]:
    out = []
    for s in sorted(stats.values(), key=lambda x: -x.hits):
        out.append(
            {
                "bot": s.bot,
                "vendor": s.vendor,
                "hits": s.hits,
                "blocked_rate": s.blocked_rate,
                "statuses": dict(s.statuses.most_common()),
                "active_days": len(s.days),
                "top_paths": s.paths.most_common(top_paths),
            }
        )
    return out


def recommendations(stats: Dict[str, BotStats]) -> List[str]:
    """Plain-language GEO recommendations derived from the crawl data."""
    recs: List[str] = []
    seen = set(stats)
    for must in ("GPTBot", "OAI-SearchBot", "PerplexityBot", "ClaudeBot"):
        if must not in seen:
            recs.append(
                f"{must} never hit the site in this log window. Check robots.txt and any WAF/CDN bot rules; "
                f"without crawling there is no citation."
            )
    for s in stats.values():
        if s.blocked_rate >= 0.3:
            recs.append(
                f"{s.bot} is blocked {int(s.blocked_rate*100)}% of the time (401/403/429). "
                f"If that is intentional, fine; if not, allow it or lower rate limits."
            )
        if s.hits and "/llms.txt" not in s.paths and "/robots.txt" in s.paths:
            recs.append(f"{s.bot} reads robots.txt but never requested /llms.txt — publish one and link it.")
    if not stats:
        recs.append("No AI crawler traffic found. Either the log window is too short or the bots are blocked upstream (CDN/WAF).")
    return recs

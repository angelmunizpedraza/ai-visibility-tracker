"""Brand / competitor detection inside AI answers.

Detection is deliberately conservative: a *mention* is a case-insensitive match
of the brand name or any alias as a whole word; a *citation* is a URL in the
answer (or in the provider's citation list) whose host matches one of the
brand's domains. Both are reported separately because they mean different
things for GEO: being mentioned is awareness, being cited is authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence
from urllib.parse import urlparse

URL_RE = re.compile(r"https?://[^\s\)\]\}>\"']+", re.IGNORECASE)


@dataclass(frozen=True)
class Brand:
    """A brand to look for. `domains` are compared against URL hosts."""

    name: str
    domains: Sequence[str] = ()
    aliases: Sequence[str] = ()

    def all_names(self) -> List[str]:
        return [self.name, *self.aliases]

    def owns_host(self, host: str) -> bool:
        host = host.lower().lstrip("www.")
        for d in self.domains:
            d = d.lower().lstrip("www.")
            if host == d or host.endswith("." + d):
                return True
        return False


@dataclass
class Detection:
    brand: str
    mentioned: bool
    mention_count: int
    cited: bool
    cited_urls: List[str] = field(default_factory=list)
    first_position: int | None = None  # character offset of first mention, lower = earlier


def extract_urls(text: str, extra: Iterable[str] = ()) -> List[str]:
    """Return unique URLs found in `text` plus any explicit citation URLs."""
    seen: List[str] = []
    for url in [*URL_RE.findall(text or ""), *extra]:
        url = url.rstrip(".,;:")
        if url and url not in seen:
            seen.append(url)
    return seen


def _word_pattern(name: str) -> re.Pattern[str]:
    # Whole-word match that tolerates punctuation around and is Unicode-aware.
    return re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.IGNORECASE)


def detect_mentions(
    text: str, brands: Sequence[Brand], citations: Iterable[str] = ()
) -> List[Detection]:
    """Detect each brand in an answer. Order of `brands` is preserved."""
    urls = extract_urls(text, citations)
    hosts = []
    for u in urls:
        try:
            hosts.append((u, urlparse(u).netloc))
        except ValueError:
            continue

    results: List[Detection] = []
    for brand in brands:
        count = 0
        first: int | None = None
        for name in brand.all_names():
            for m in _word_pattern(name).finditer(text or ""):
                count += 1
                if first is None or m.start() < first:
                    first = m.start()
        cited_urls = [u for u, h in hosts if brand.owns_host(h)]
        results.append(
            Detection(
                brand=brand.name,
                mentioned=count > 0,
                mention_count=count,
                cited=bool(cited_urls),
                cited_urls=cited_urls,
                first_position=first,
            )
        )
    return results

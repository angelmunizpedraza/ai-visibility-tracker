"""ai-visibility-tracker — measure how often a brand is cited by AI answer engines.

Track a set of prompts across ChatGPT, Perplexity and Claude, detect brand and
competitor mentions/citations, compute share of voice over time, and analyse
server logs to see which AI crawlers actually visit your site.
"""

__version__ = "0.1.0"

from .detect import Brand, detect_mentions, extract_urls  # noqa: F401
from .metrics import share_of_voice, summarize_run  # noqa: F401

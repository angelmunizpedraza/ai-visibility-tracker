# ai-visibility-tracker

**Measure whether AI answer engines mention and cite your brand — and whether their crawlers can even reach your site.**

[![CI](https://github.com/angelmunizpedraza/ai-visibility-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/angelmunizpedraza/ai-visibility-tracker/actions)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Search is moving from ten blue links to a single generated answer. Classic rank trackers cannot tell you whether ChatGPT, Perplexity or Claude recommend you when someone asks *"best veterinarian for bulldogs in Los Angeles"*. This tool does, and it does it the way SEO teams already work: a list of prompts, a list of brands, a database, a report, a webhook.

```
$ aivis track --config brands.json --providers chatgpt,perplexity,claude --md report.md

# AI visibility report — run #7
| Brand                    | Mention rate | Citation rate | Share of voice | Δ SoV vs previous |
|--------------------------|-------------:|--------------:|---------------:|------------------:|
| Los Angeles Bulldog Vet  |         67 % |          33 % |           34 % |            +9 pt  |
| VCA Animal Hospitals     |         67 % |          67 % |           34 % |            -4 pt  |
| Banfield Pet Hospital    |         60 % |           0 % |           31 % |            -5 pt  |

## Gaps — competitor cited, you are not (3)
- perplexity · "Affordable bulldog specialist near Santa Monica" → VCA Animal Hospitals
```

## What it measures

| Metric | Meaning | Why it matters for GEO |
|---|---|---|
| **Mention rate** | % of prompts where the answer names the brand (whole-word, aliases included) | Awareness inside the answer |
| **Citation rate** | % of prompts where the answer links to one of the brand's domains (in text or in the engine's citation list) | Authority: the engine trusts you as a source |
| **Share of voice** | Brand mentions ÷ mentions of all tracked brands | Your slice of the answer vs competitors |
| **Gaps** | Prompts where a competitor is mentioned and you are not | The highest-value content opportunities |
| **Δ vs previous run** | Change since the last run with the same label | Did last week's changes move anything? |
| **AI crawler report** | Hits, blocked rate, active days and top paths per AI bot from your access logs | No crawl → no citation. Most teams never check this |

## Install

```bash
pip install git+https://github.com/angelmunizpedraza/ai-visibility-tracker.git
# YAML configs:
pip install "ai-visibility-tracker[yaml] @ git+https://github.com/angelmunizpedraza/ai-visibility-tracker.git"
```

Set the keys for the engines you want (only those):

```bash
export OPENAI_API_KEY=...       # chatgpt   (gpt-4o-mini by default)
export PERPLEXITY_API_KEY=...   # perplexity (sonar; returns real citations)
export ANTHROPIC_API_KEY=...    # claude    (claude-3-5-haiku-latest)
```

No keys? `--dry-run` uses deterministic synthetic answers so you can see the whole pipeline work.

## Usage

### 1. Track brands across engines

```yaml
# brands.yaml
label: vet-la-weekly            # runs with the same label are compared over time
brands:
  - name: Los Angeles Bulldog Vet
    domains: [losangelesbulldogvet.com]
    aliases: ["LA Bulldog Vet"]
  - name: VCA Animal Hospitals
    domains: [vcahospitals.com]
    aliases: [VCA]
prompts:
  - Best veterinarian for English bulldogs in Los Angeles
  - Where can I get BOAS surgery for my bulldog in LA?
```

```bash
aivis track --config brands.yaml --providers chatgpt,perplexity \
  --db visibility.db --md report.md --csv answers.csv --json summary.json \
  --webhook https://n8n.example.com/webhook/ai-visibility
```

The first brand in the list is treated as *yours* for the gap analysis. Every answer, detection and URL is stored in SQLite so you can audit exactly what the engine said.

### 2. See the trend

```bash
aivis history --db visibility.db --brand "Los Angeles Bulldog Vet" --provider perplexity
| run | date       | engine     | mention rate | citation rate | prompts |
|----:|------------|------------|-------------:|--------------:|--------:|
|   1 | 2026-08-03 | perplexity |         20 % |           0 % |       5 |
|   4 | 2026-08-24 | perplexity |         60 % |          20 % |       5 |
|   7 | 2026-09-14 | perplexity |        100 % |          40 % |       5 |
```

### 3. Check that AI crawlers can actually reach you

```bash
aivis logs /var/log/nginx/access.log /var/log/nginx/access.log.1.gz --md crawlers.md
```

```
| Bot           | Vendor                 | Hits | Blocked | Active days | Top path            |
|---------------|------------------------|-----:|--------:|------------:|---------------------|
| GPTBot        | OpenAI (training)      |  312 |     0 % |          14 | `/services/`        |
| PerplexityBot | Perplexity (index)     |   41 |   100 % |           6 | `/blog/bulldog-boas/` |
| ClaudeBot     | Anthropic (training)   |   18 |     0 % |           3 | `/robots.txt`       |

## Recommendations
- PerplexityBot is blocked 100% of the time (401/403/429). If that is intentional, fine; if not, allow it or lower rate limits.
- ClaudeBot reads robots.txt but never requested /llms.txt — publish one and link it.
```

Recognises 20+ AI user agents (GPTBot, OAI-SearchBot, ChatGPT-User, ClaudeBot, Claude-SearchBot, PerplexityBot, Google-Extended, Applebot-Extended, Bytespider, CCBot, meta-externalagent…). Reads plain and `.gz` logs in combined format.

### 4. Automate it

A cron line + the webhook is enough to get a weekly share-of-voice message in Slack/WhatsApp via n8n:

```cron
0 7 * * 1  cd /opt/aivis && aivis track --config brands.yaml --providers chatgpt,perplexity --webhook $N8N_HOOK --md /var/www/reports/ai-visibility.md
```

The webhook payload contains `run_id`, `label`, the full `summary` (overall, by_provider, gaps, delta) and the rendered `markdown`.

## How detection works (and its limits)

* A **mention** is a case-insensitive whole-word match of the brand name or any alias. `VCAX` does not match `VCA`.
* A **citation** is a URL whose host equals a brand domain or a subdomain of it (`www.` ignored). `notlosangelesbulldogvet.com` is not a citation for `losangelesbulldogvet.com`.
* Perplexity returns an explicit citation list; it is merged with URLs found in the text. ChatGPT and Claude only cite when their answer includes URLs, which the system prompt asks for.
* LLM answers are not deterministic. Use enough prompts (20+) and compare runs with the same label over weeks, not single answers.
* Costs: one run = prompts × engines requests. With small models (gpt-4o-mini, sonar, haiku) 25 prompts × 3 engines costs cents.

## Project layout

```
ai_visibility_tracker/
  providers.py   # ChatGPT, Perplexity, Claude via plain requests; FakeProvider for tests
  detect.py      # Brand, mention/citation detection
  metrics.py     # share of voice, deltas, gap analysis
  store.py       # SQLite schema and queries (runs, answers, detections, history)
  logs.py        # AI-crawler analysis of access logs + recommendations
  report.py      # Markdown / CSV / webhook
  cli.py         # aivis track | logs | history
tests/           # 23 tests, no network needed
examples/        # sample config (JSON + YAML) and sample access log
```

## Development

```bash
git clone https://github.com/angelmunizpedraza/ai-visibility-tracker.git
cd ai-visibility-tracker
pip install -e ".[dev]"
pytest -q
```

## Related tools by the same author

* [seo-audit](https://github.com/angelmunizpedraza/seo-audit) — crawl a site and get severity-ranked technical SEO issues.
* [geo-check](https://github.com/angelmunizpedraza/geo-check) — score how ready a site is for AI search (robots for AI bots, llms.txt, structured data, no-JS readability).
* [ga4-report](https://github.com/angelmunizpedraza/ga4-report) — organic traffic report from the GA4 Data API with period comparison and landing-page alerts.
* [llms-txt-generator](https://github.com/angelmunizpedraza/llms-txt-generator) — generate an `llms.txt` for any site.

Together they cover the full GEO loop: **make the site readable by AI (geo-check, llms-txt-generator) → verify the bots come (aivis logs) → measure whether the engines cite you (aivis track) → tie it to traffic (ga4-report).**

## License

MIT © Ángel Muñiz Pedraza — [LinkedIn](https://www.linkedin.com/in/angel-muniz-seo)

"""Command-line interface.

    aivis track  --config brands.yaml --providers chatgpt,perplexity [--db visibility.db] [--md report.md] [--csv out.csv] [--webhook URL]
    aivis logs   access.log [access.log.2.gz ...] [--md crawlers.md]
    aivis history --db visibility.db --brand "My Brand" [--provider chatgpt]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from . import __version__
from .config import load_config
from .detect import detect_mentions
from .logs import analyse, iter_lines, recommendations, to_report
from .metrics import summarize_run
from .providers import FakeProvider, ProviderError, build_providers
from .report import csv_rows, logs_markdown, markdown_report, post_webhook
from .store import Store


def _demo_provider(name: str, cfg) -> FakeProvider:
    """Deterministic synthetic answers so --dry-run produces a realistic report."""
    import hashlib

    answers, cites = {}, {}
    for prompt in cfg.prompts:
        mentioned = []
        for b in cfg.brands:
            h = int(hashlib.sha1(f"{name}|{prompt}|{b.name}".encode()).hexdigest(), 16)
            if h % 3:  # ~2/3 of the time the brand is mentioned
                mentioned.append(b)
        text = "Good options: " + ", ".join(b.name for b in mentioned) + "." if mentioned else "Hard to say."
        answers[prompt] = text
        cites[prompt] = [f"https://{b.domains[0]}/" for b in mentioned if b.domains and len(b.name) % 2 == 0]
    return FakeProvider(answers, cites, name=name)


def _cmd_track(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if args.dry_run:
        providers = [_demo_provider(n, cfg) for n in args.providers.split(",")]
    else:
        providers = build_providers(args.providers.split(","))

    store = Store(args.db)
    run_id = store.new_run(label=cfg.label)
    errors = 0
    for prompt in cfg.prompts:
        for prov in providers:
            try:
                ans = prov.ask(prompt)
            except ProviderError as e:  # keep going; one failing engine must not kill the run
                errors += 1
                print(f"[warn] {prov.name}: {e}", file=sys.stderr)
                continue
            dets = detect_mentions(ans.text, cfg.brands, ans.citations)
            store.save_answer(run_id, ans, dets)
            if args.verbose:
                flags = " ".join(f"{d.brand}:{'M' if d.mentioned else '-'}{'C' if d.cited else '-'}" for d in dets)
                print(f"[{prov.name}] {prompt[:60]!r} -> {flags}")

    rows = store.run_rows(run_id)
    prev_id = store.previous_run_id(run_id, cfg.label)
    prev_rows = store.run_rows(prev_id) if prev_id else None
    summary = summarize_run(rows, prev_rows)
    brand_names = [b.name for b in cfg.brands]
    md = markdown_report(summary, run_id, brand_names, [p.name for p in providers], len(cfg.prompts))

    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    if args.csv:
        Path(args.csv).write_text(csv_rows(rows), encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps({"run_id": run_id, "summary": summary}, indent=2, default=str), encoding="utf-8")
    if args.webhook:
        status = post_webhook(args.webhook, {"run_id": run_id, "label": cfg.label, "summary": summary, "markdown": md})
        print(f"[webhook] HTTP {status}", file=sys.stderr)
    if not (args.md or args.csv or args.json):
        print(md)
    store.close()
    return 1 if errors and errors == len(cfg.prompts) * len(providers) else 0


def _cmd_logs(args: argparse.Namespace) -> int:
    def all_lines():
        for f in args.files:
            yield from iter_lines(f)

    stats = analyse(all_lines(), top_paths=args.top)
    report = to_report(stats, top_paths=args.top)
    recs = recommendations(stats)
    md = logs_markdown(report, recs)
    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps({"bots": report, "recommendations": recs}, indent=2), encoding="utf-8")
    if not (args.md or args.json):
        print(md)
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    store = Store(args.db)
    rows = store.history(args.brand, args.provider)
    store.close()
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    print("| run | date | engine | mention rate | citation rate | prompts |")
    print("|---:|---|---|---:|---:|---:|")
    for r in rows:
        print(f"| {r['run_id']} | {r['started_at'][:10]} | {r['provider']} | {r['mention_rate']*100:.0f} % | {r['citation_rate']*100:.0f} % | {r['prompts']} |")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aivis", description="Measure brand visibility inside AI answer engines.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("track", help="Ask every prompt to every engine and score brand mentions/citations")
    t.add_argument("--config", required=True, help="YAML/JSON file with brands and prompts")
    t.add_argument("--providers", default="chatgpt,perplexity", help="Comma list: chatgpt,perplexity,claude")
    t.add_argument("--db", default="visibility.db")
    t.add_argument("--md")
    t.add_argument("--csv")
    t.add_argument("--json")
    t.add_argument("--webhook", help="POST the summary to this URL (n8n, Make, Zapier)")
    t.add_argument("--dry-run", action="store_true", help="Use fake providers (no API calls, no keys needed)")
    t.add_argument("-v", "--verbose", action="store_true")
    t.set_defaults(func=_cmd_track)

    l = sub.add_parser("logs", help="Analyse AI crawler traffic in access logs")
    l.add_argument("files", nargs="+")
    l.add_argument("--top", type=int, default=10)
    l.add_argument("--md")
    l.add_argument("--json")
    l.set_defaults(func=_cmd_logs)

    h = sub.add_parser("history", help="Time series of a brand's visibility across runs")
    h.add_argument("--db", default="visibility.db")
    h.add_argument("--brand", required=True)
    h.add_argument("--provider")
    h.add_argument("--json", action="store_true")
    h.set_defaults(func=_cmd_history)
    return p


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ProviderError, FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

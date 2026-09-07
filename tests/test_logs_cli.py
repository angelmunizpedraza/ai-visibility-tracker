import gzip
import json

from ai_visibility_tracker import cli
from ai_visibility_tracker.logs import analyse, identify_bot, parse_line, recommendations, to_report

LINE = '66.249.66.1 - - [10/Sep/2026:08:14:22 +0000] "GET /services/ HTTP/1.1" 200 5123 "-" "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)"'
BLOCKED = '66.249.66.1 - - [11/Sep/2026:09:00:00 +0000] "GET /blog/ HTTP/1.1" 403 0 "-" "PerplexityBot/1.0 (+https://perplexity.ai/perplexitybot)"'
ROBOTS = '1.2.3.4 - - [11/Sep/2026:09:00:01 +0000] "GET /robots.txt HTTP/1.1" 200 120 "-" "ClaudeBot/1.0"'
HUMAN = '5.6.7.8 - - [11/Sep/2026:09:00:02 +0000] "GET / HTTP/1.1" 200 9000 "-" "Mozilla/5.0 (Windows NT 10.0) Chrome/128.0"'


def test_parse_line_and_day():
    rec = parse_line(LINE)
    assert rec["path"] == "/services/" and rec["status"] == "200" and rec["day"] == "2026-Sep-10"


def test_identify_bot_known_and_unknown():
    assert identify_bot("something GPTBot/1.2 here") == "GPTBot"
    assert identify_bot("Mozilla/5.0 Chrome/128") is None


def test_analyse_counts_only_ai_bots_and_blocked_rate():
    stats = analyse([LINE, BLOCKED, ROBOTS, HUMAN, "garbage line"])
    assert set(stats) == {"GPTBot", "PerplexityBot", "ClaudeBot"}
    assert stats["PerplexityBot"].blocked_rate == 1.0
    rep = to_report(stats)
    assert rep[0]["hits"] == 1 and "vendor" in rep[0]


def test_recommendations_flag_missing_blocked_and_llms_txt():
    stats = analyse([BLOCKED, ROBOTS])
    recs = "\n".join(recommendations(stats))
    assert "GPTBot never hit" in recs
    assert "PerplexityBot is blocked 100%" in recs
    assert "ClaudeBot reads robots.txt but never requested /llms.txt" in recs


def test_cli_logs_reads_gzip(tmp_path, capsys):
    p = tmp_path / "access.log.gz"
    with gzip.open(p, "wt") as fh:
        fh.write(LINE + "\n" + HUMAN + "\n")
    assert cli.main(["logs", str(p)]) == 0
    out = capsys.readouterr().out
    assert "GPTBot" in out and "OpenAI" in out


def test_cli_track_dry_run_end_to_end(tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({
        "label": "test",
        "brands": [{"name": "Acme", "domains": ["acme.com"]}, "Globex"],
        "prompts": ["best crm for vets?", "cheapest crm?"],
    }))
    md = tmp_path / "r.md"
    js = tmp_path / "r.json"
    csvf = tmp_path / "r.csv"
    code = cli.main(["track", "--config", str(cfg), "--providers", "chatgpt,claude", "--dry-run",
                     "--db", str(tmp_path / "v.db"), "--md", str(md), "--json", str(js), "--csv", str(csvf)])
    assert code == 0
    assert "# AI visibility report — run #1" in md.read_text()
    data = json.loads(js.read_text())
    assert set(data["summary"]["by_provider"]) == {"chatgpt", "claude"}
    assert csvf.read_text().count("\n") == 1 + 2 * 2 * 2  # header + prompts*providers*brands


def test_cli_track_rejects_unknown_provider(tmp_path, capsys):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"brands": ["A"], "prompts": ["q"]}))
    assert cli.main(["track", "--config", str(cfg), "--providers", "bing", "--db", str(tmp_path / "v.db")]) == 2
    assert "Unknown provider" in capsys.readouterr().err


def test_cli_config_validation(tmp_path):
    cfg = tmp_path / "bad.json"
    cfg.write_text(json.dumps({"brands": [], "prompts": ["q"]}))
    assert cli.main(["track", "--config", str(cfg), "--dry-run", "--db", str(tmp_path / "v.db")]) == 2

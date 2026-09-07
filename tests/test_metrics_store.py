import json

from ai_visibility_tracker.detect import Brand, detect_mentions
from ai_visibility_tracker.metrics import gaps, share_of_voice, summarize_run
from ai_visibility_tracker.providers import FakeProvider
from ai_visibility_tracker.store import Store

ME = Brand("Acme", domains=["acme.com"])
RIVAL = Brand("Globex", domains=["globex.com"])


def rows(*items):
    # (provider, prompt, brand, mentioned, cited)
    return [
        {"provider": p, "prompt": q, "brand": b, "mentioned": m, "cited": c, "mention_count": m, "cited_urls": "[]", "first_position": None}
        for p, q, b, m, c in items
    ]


def test_share_of_voice_basic():
    sov = share_of_voice(rows(("x", "q1", "Acme", 1, 1), ("x", "q1", "Globex", 1, 0), ("x", "q2", "Acme", 0, 0), ("x", "q2", "Globex", 1, 1)))
    assert sov["Acme"]["mention_rate"] == 0.5
    assert sov["Acme"]["citation_rate"] == 0.5
    assert sov["Globex"]["mention_rate"] == 1.0
    assert sov["Acme"]["share_of_voice"] == round(1 / 3, 4)
    assert sov["Globex"]["share_of_voice"] == round(2 / 3, 4)


def test_share_of_voice_no_mentions_is_zero_not_error():
    sov = share_of_voice(rows(("x", "q1", "Acme", 0, 0)))
    assert sov["Acme"]["share_of_voice"] == 0.0


def test_gaps_lists_prompts_where_only_rival_appears():
    g = gaps(rows(("x", "q1", "Acme", 0, 0), ("x", "q1", "Globex", 1, 0), ("x", "q2", "Acme", 1, 0), ("x", "q2", "Globex", 1, 0)))
    assert g == [{"provider": "x", "prompt": "q1", "competitors_mentioned": ["Globex"]}]


def test_summarize_run_delta_against_previous():
    prev = rows(("x", "q1", "Acme", 0, 0), ("x", "q1", "Globex", 1, 0))
    cur = rows(("x", "q1", "Acme", 1, 1), ("x", "q1", "Globex", 1, 0))
    s = summarize_run(cur, prev)
    assert s["delta"]["Acme"]["mention_rate"] == 1.0
    assert s["delta"]["Acme"]["share_of_voice"] == 0.5
    assert "by_provider" in s and "x" in s["by_provider"]


def test_store_roundtrip_and_history(tmp_path):
    store = Store(tmp_path / "t.db")
    prov = FakeProvider({"best crm?": "Try Acme (https://acme.com) or Globex."})
    run1 = store.new_run("weekly")
    ans = prov.ask("best crm?")
    store.save_answer(run1, ans, detect_mentions(ans.text, [ME, RIVAL], ans.citations))
    r = store.run_rows(run1)
    assert len(r) == 2
    acme = [x for x in r if x["brand"] == "Acme"][0]
    assert acme["mentioned"] == 1 and acme["cited"] == 1
    assert json.loads(acme["cited_urls"]) == ["https://acme.com"]

    run2 = store.new_run("weekly")
    store.save_answer(run2, prov.ask("best crm?"), detect_mentions("Globex only.", [ME, RIVAL]))
    assert store.previous_run_id(run2, "weekly") == run1
    hist = store.history("Acme")
    assert [h["run_id"] for h in hist] == [run1, run2]
    assert hist[0]["mention_rate"] == 1.0 and hist[1]["mention_rate"] == 0.0
    store.close()

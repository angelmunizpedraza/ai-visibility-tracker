from ai_visibility_tracker.detect import Brand, detect_mentions, extract_urls


B = Brand("Los Angeles Bulldog Vet", domains=["losangelesbulldogvet.com"], aliases=["LA Bulldog Vet"])
C = Brand("VCA", domains=["vcahospitals.com"])


def test_extract_urls_dedupes_and_strips_punctuation():
    text = "See https://a.com/x. Also https://a.com/x, and (https://b.org/y)."
    assert extract_urls(text) == ["https://a.com/x", "https://b.org/y"]


def test_extract_urls_merges_explicit_citations():
    assert extract_urls("no links", ["https://c.net"]) == ["https://c.net"]


def test_mention_is_whole_word_and_case_insensitive():
    text = "For bulldogs in LA, los angeles bulldog vet is a solid option."
    d = detect_mentions(text, [B])[0]
    assert d.mentioned and d.mention_count == 1 and d.first_position == 20


def test_alias_counts_as_mention():
    d = detect_mentions("Try LA Bulldog Vet.", [B])[0]
    assert d.mentioned and d.mention_count == 1


def test_partial_word_does_not_match():
    d = detect_mentions("VCAX is unrelated", [C])[0]
    assert not d.mentioned


def test_citation_by_domain_including_subdomain_and_www():
    text = "Sources: https://www.losangelesbulldogvet.com/services and https://blog.vcahospitals.com/post"
    dets = detect_mentions(text, [B, C])
    assert dets[0].cited and dets[0].cited_urls == ["https://www.losangelesbulldogvet.com/services"]
    assert dets[1].cited


def test_citation_from_provider_list_without_text_mention():
    d = detect_mentions("A good clinic exists.", [B], citations=["https://losangelesbulldogvet.com"])[0]
    assert d.cited and not d.mentioned


def test_lookalike_domain_is_not_a_citation():
    d = detect_mentions("https://notlosangelesbulldogvet.com", [B])[0]
    assert not d.cited


def test_order_of_brands_preserved():
    dets = detect_mentions("", [C, B])
    assert [d.brand for d in dets] == ["VCA", "Los Angeles Bulldog Vet"]


def test_empty_text_safe():
    dets = detect_mentions("", [B])
    assert dets[0].mention_count == 0 and dets[0].first_position is None

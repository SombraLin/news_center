from app.domain.identity import build_content_hash, canonicalize_url


def test_canonicalize_url_removes_tracking_and_fragment():
    value = canonicalize_url(
        "HTTPS://Example.COM:443/news/1?utm_source=zaker&b=2&a=1#from-app"
    )
    assert value == "https://example.com/news/1?a=1&b=2"


def test_canonicalize_url_preserves_semantic_query_params():
    value = canonicalize_url("https://example.com/search?q=ai&page=2")
    assert value == "https://example.com/search?page=2&q=ai"


def test_content_hash_normalizes_case_width_and_whitespace():
    first = build_content_hash(" OpenAI  发布新品 ", "摘要　内容")
    second = build_content_hash("openai 发布新品", "摘要 内容")
    assert first == second

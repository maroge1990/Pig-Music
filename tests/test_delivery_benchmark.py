from scripts.benchmark_delivery import measure


def test_delivery_benchmark_uses_authenticated_fixture_and_conditional_reads(
    monkeypatch,
):
    monkeypatch.delenv("PIG_MUSIC_TEST_LEGACY_API", raising=False)
    result = measure(100)
    assert result["tracks"] == 100 and result["albums"] == 10
    assert result["gzip_bytes"] < result["json_bytes"]
    assert result["conditional_p95_ms"] >= 0

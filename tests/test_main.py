import os
import tempfile

from main import load_config, load_feeds_file


def test_load_feeds_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("# comment\n")
        f.write("https://example.com/rss\n")
        f.write("https://example.jp/feed,ja,日本語フィード\n")
        f.write("\n")
    try:
        feeds = load_feeds_file(f.name)
        assert len(feeds) == 2
        assert feeds[0]["url"] == "https://example.com/rss"
        assert feeds[0]["lang"] == "en"
        assert feeds[1]["lang"] == "ja"
        assert feeds[1]["name"] == "日本語フィード"
    finally:
        os.unlink(f.name)


def test_load_config():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("feeds:\n  - name: Test\n    url: https://example.com/rss\n    lang: en\nwindow_days: 5\n")
    try:
        config = load_config(f.name)
        assert config["window_days"] == 5
        assert len(config["feeds"]) == 1
        assert config["feeds"][0]["name"] == "Test"
    finally:
        os.unlink(f.name)

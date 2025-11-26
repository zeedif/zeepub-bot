import importlib.util
import os

from config.config_settings import config


def test_get_recent_links(tmp_path):
    db_file = tmp_path / "url_cache_recent.db"
    config.URL_CACHE_DB_PATH = str(db_file)

    spec = importlib.util.spec_from_file_location("uc", os.path.join(os.path.dirname(__file__), "..", "utils", "url_cache.py"))
    uc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(uc)

    # Create some mappings
    hashes = []
    for i in range(5):
        h = uc.create_short_url(f"https://example.com/book{i}.epub", book_title=f"book{i}")
        hashes.append(h)

    recent = uc.get_recent_links(limit=3)
    assert len(recent) == 3
    # Ensure returned entries look correct and include at least one of our created URLs
    assert len(recent) == 3
    returned_urls = [r[1] for r in recent]
    # At least one of our created URLs should appear among the recent results
    assert any(u in [f"https://example.com/book{i}.epub" for i in range(5)] for u in returned_urls)

import asyncio
import importlib.util
import os
import time

from config.config_settings import config


def test_get_candidates_and_validator(tmp_path, monkeypatch):
    # Use a fresh DB
    db_file = tmp_path / "url_cache_validator.db"
    config.URL_CACHE_DB_PATH = str(db_file)
    # Force SQLite mode by clearing DATABASE_URL
    monkeypatch.setattr(config, 'DATABASE_URL', None)

    # Load module directly
    spec = importlib.util.spec_from_file_location("url_cache_mod", os.path.join(os.path.dirname(__file__), "..", "utils", "url_cache.py"))
    url_cache = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(url_cache)
    
    # Initialize the database
    url_cache.init_db()

    # create entries
    h1 = url_cache.create_short_url("https://example.com/one.epub", book_title="one")
    h2 = url_cache.create_short_url("https://example.com/two.epub", book_title="two")

    # Force mark h2 as invalid by updating DB directly
    conn = url_cache._get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE url_mappings SET is_valid = 0 WHERE hash = ?", (h2,))
    conn.commit()
    conn.close()

    # candidates should include entries that are invalid
    c = url_cache.get_candidates_for_validation(limit=10, older_than_seconds=1)
    assert isinstance(c, list)
    assert any(h2 == x[0] for x in c)

    # Start validator and cancel quickly (smoke test)
    # Ensure url_cache is importable as utils.url_cache so relative imports work
    import sys
    sys.modules['utils.url_cache'] = url_cache

    spec2 = importlib.util.spec_from_file_location("utils.url_validator", os.path.join(os.path.dirname(__file__), "..", "utils", "url_validator.py"))
    url_validator = importlib.util.module_from_spec(spec2)
    sys.modules['utils.url_validator'] = url_validator
    spec2.loader.exec_module(url_validator)

    loop = asyncio.get_event_loop()
    task = url_validator.start_background_validator(loop=loop, interval=1, batch_size=5)
    # let it run one cycle
    time.sleep(1.2)
    url_validator.stop_background_validator()
    assert task is not None

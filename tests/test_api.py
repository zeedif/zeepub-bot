import sys
from unittest.mock import MagicMock, AsyncMock

# Mockear dependencias ANTES de importar api.main
# Esto es crucial porque api.main instancia ZeePubBot al nivel de módulo
mock_bot_module = MagicMock()
sys.modules["core.bot"] = mock_bot_module
mock_bot_class = MagicMock()
mock_bot_module.ZeePubBot = mock_bot_class
mock_bot_instance = MagicMock()
mock_bot_class.return_value = mock_bot_instance
mock_bot_instance.initialize = AsyncMock()
mock_bot_instance.start_async = AsyncMock()
mock_bot_instance.stop_async = AsyncMock()

from fastapi.testclient import TestClient
from api.main import app
import pytest

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "ZeePub Bot API is running"}

def test_get_feed_no_url():
    # Mockear parse_feed_from_url
    with pytest.MonkeyPatch.context() as m:
        mock_parse = AsyncMock()
        mock_feed = MagicMock()
        mock_feed.feed.title = "Test Feed"
        entry = MagicMock()
        entry.title = "Book 1"
        entry.author = "Author 1"
        entry.id = "1"
        entry.summary = "Summary"
        entry.links = [{"href": "http://cover.jpg", "rel": "http://opds-spec.org/image", "type": "image/jpeg"}]
        # feedparser entries allow dict access too, but getattr is used in code
        # To support entry.get(), we need to mock __getitem__? 
        # The code uses entry.get("title") AND getattr(entry, "links").
        # Let's make it support both or fix the code to be consistent.
        # Actually, code uses: entry.get("title") ... getattr(entry, "links")
        # So entry needs to be an object with attributes AND a get method.
        entry.get = lambda k, d=None: getattr(entry, k, d)
        
        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed
        
        m.setattr("api.routes.parse_feed_from_url", mock_parse)
        
        response = client.get("/api/feed")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Feed"
        assert len(data["entries"]) == 1
        assert data["entries"][0]["title"] == "Book 1"
        assert data["entries"][0]["cover_url"] == "http://cover.jpg"

def test_search_books():
    with pytest.MonkeyPatch.context() as m:
        mock_parse = AsyncMock()
        mock_feed = MagicMock()
        mock_feed.feed.title = "Search Results"
        mock_feed.entries = []
        mock_parse.return_value = mock_feed
        
        m.setattr("api.routes.parse_feed_from_url", mock_parse)
        
        response = client.get("/api/search?q=harry")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Search Results"

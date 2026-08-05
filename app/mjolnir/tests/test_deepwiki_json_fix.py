"""Test that DeepWiki client handles non-JSON MCP server responses."""
import os, sys, json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from providers.deepwiki.client import DeepWikiClient


def test_client_logs_raw_response_on_json_error(caplog):
    """When the MCP server returns non-JSON, log the raw response body."""
    client = DeepWikiClient("test/repo", mcp_url="http://localhost/test")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "not json at all"
    mock_response.json.side_effect = ValueError("Expecting value")

    with patch("httpx.post", return_value=mock_response):
        import logging
        with caplog.at_level(logging.WARNING):
            result = client.read_wiki_structure()
        assert "DeepWiki non-JSON response" in caplog.text
        assert "not json at all" in caplog.text


def test_client_handles_empty_response():
    """Empty response body should not crash."""
    client = DeepWikiClient("test/repo", mcp_url="http://localhost/test")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = ""
    mock_response.json.side_effect = ValueError("Expecting value: line 1 column 1")

    with patch("httpx.post", return_value=mock_response):
        result = client.read_wiki_structure()
        assert "unavailable" in result.lower()


def test_client_handles_406_not_acceptable():
    """406 with SSE requirement should not crash."""
    client = DeepWikiClient("test/repo", mcp_url="http://localhost/test")
    mock_response = MagicMock()
    mock_response.status_code = 406
    mock_response.text = '{"error":"Not Acceptable"}'
    mock_response.json.side_effect = ValueError("Expecting value")

    with patch("httpx.post", return_value=mock_response):
        result = client.read_wiki_structure()
        assert "unavailable" in result.lower()

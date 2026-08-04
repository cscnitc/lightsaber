"""Tests for DeepWiki MCP client."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from providers.deepwiki.client import DeepWikiClient, DeepWikiContextStatus


def test_deepwiki_client_creates_with_repo_name():
    client = DeepWikiClient("chipsalliance/mjolnir")
    assert client.repo_name == "chipsalliance/mjolnir"


def test_deepwiki_client_has_read_wiki_structure_tool():
    client = DeepWikiClient("chipsalliance/mjolnir")
    tool = client.get_tool_definition("read_wiki_structure")
    assert tool is not None
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "read_wiki_structure"


def test_deepwiki_client_has_ask_question_tool():
    client = DeepWikiClient("chipsalliance/mjolnir")
    tool = client.get_tool_definition("ask_question")
    assert tool is not None
    assert "repoName" in str(tool["function"]["parameters"])
    assert "question" in str(tool["function"]["parameters"])


def test_deepwiki_handles_unavailable_service():
    client = DeepWikiClient("chipsalliance/mjolnir", mcp_url="https://invalid.example.com/nonexistent")
    result = client.read_wiki_structure()
    assert result.startswith("DeepWiki unavailable")


def test_context_status_values_exist():
    for status in DeepWikiContextStatus:
        assert status.value in [
            "verified", "revision-unverified", "unindexed",
            "unauthorized", "unavailable", "not-applicable",
        ]

"""Tests for OpenAI provider client initialization."""
import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from providers.openai.client import get_client


def test_get_client_returns_none_when_api_key_not_set(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = get_client()
    assert client is None


def test_get_client_creates_client_with_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    client = get_client()
    assert client is not None


def test_get_client_uses_custom_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://custom.api.example.com/v1")
    client = get_client()
    assert client is not None
    assert str(client.base_url).rstrip("/") == "https://custom.api.example.com/v1"

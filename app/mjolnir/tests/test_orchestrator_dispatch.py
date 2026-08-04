"""Test that the main orchestrator routes to the openai provider."""
import os
import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_main_py_imports_openai_provider():
    """Verify main.py can import the openai provider module."""
    import providers.openai.main as openai_provider
    assert hasattr(openai_provider, "run_analysis")
    assert callable(openai_provider.run_analysis)


def test_main_py_dispatches_to_openai_provider():
    """Verify the dispatch path exists for 'openai' provider in main.py."""
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    source = main_path.read_text()
    assert "elif provider_name == \"openai\"" in source
    assert "providers.openai.main" in source

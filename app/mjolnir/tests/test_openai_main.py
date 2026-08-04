"""Tests for openai provider main.py run_analysis entry point."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from providers.openai.client import get_client
from providers.openai.agents.auditor import OpenAIAuditorAgent
from providers.openai.agents.adversarial_reviewer import OpenAIAdversarialReviewerAgent


def _has_api_key():
    return bool(os.environ.get("OPENAI_API_KEY"))


def test_adversarial_reviewer_creates_with_instruction():
    client = get_client()
    reviewer = OpenAIAdversarialReviewerAgent(
        client, "gpt-5.6-sol", "Verify these findings.", code_dir="."
    )
    assert reviewer is not None
    assert reviewer.system_instruction == "Verify these findings."
    assert reviewer.code_dir == "."
    assert len(reviewer.tools) > 0


@pytest.mark.skipif(not _has_api_key(), reason="OPENAI_API_KEY not set")
def test_adversarial_reviewer_runs_against_finding():
    client = get_client()
    reviewer = OpenAIAdversarialReviewerAgent(
        client, "gpt-5.6-sol",
        "You are an adversarial security reviewer. Review the vulnerability finding "
        "and respond with valid JSON containing: title, severity (one of: Critical, High, "
        "Medium, Low, Informational), location, description, recommendation, "
        "verdict (one of: Exploitable, Not Exploitable, False Positive), "
        "justification, and attack_vector.",
        code_dir=".",
    )
    import json
    from data.review_finding import ReviewFinding

    finding = {
        "title": "Key validity check bypass",
        "severity": "High",
        "location": "keymgr_input_checks.sv:69",
        "description": "key_vld_o ignores key_i.valid signal. Only checks share non-zero.",
        "recommendation": "Include key_i.valid in validity computation.",
    }
    result = reviewer.run(json.dumps(finding))
    assert isinstance(result, ReviewFinding)
    assert result.verdict is not None


def test_run_analysis_signature_is_importable():
    """Verify the run_analysis function can be imported."""
    from providers.openai.main import run_analysis
    assert callable(run_analysis)

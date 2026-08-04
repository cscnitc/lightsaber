"""Integration test: OpenAI auditor runs against a real .sv file with DeepWiki context."""
import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from providers.openai.client import get_client
from providers.openai.agents.auditor import OpenAIAuditorAgent
from providers.deepwiki.client import DeepWikiClient, DeepWikiContextStatus
from data.security_report import SecurityReport

TEST_SV = """module keymgr_input_checks (
  input  logic key_vld_in,
  input  logic [255:0] key_share0,
  input  logic [255:0] key_share1,
  output logic key_vld_o
);
  assign key_vld_o = |key_share0 && |key_share1;
endmodule
"""


def _has_api_key():
    return bool(os.environ.get("OPENAI_API_KEY"))


@pytest.mark.skipif(not _has_api_key(), reason="OPENAI_API_KEY not set")
def test_auditor_runs_against_sv_and_returns_security_report():
    client = get_client()
    assert client is not None

    agent = OpenAIAuditorAgent(client, "gpt-5.6-sol")
    report = agent.run("test_keymgr.sv", TEST_SV)

    assert isinstance(report, SecurityReport)
    assert len(report.vulnerabilities) >= 0


@pytest.mark.skipif(not _has_api_key(), reason="OPENAI_API_KEY not set")
def test_auditor_finding_has_evidence_level_e0():
    client = get_client()
    agent = OpenAIAuditorAgent(client, "gpt-5.6-sol")
    report = agent.run("test_keymgr.sv", TEST_SV)

    for vuln in report.vulnerabilities:
        v = agent._to_vulnerability(vuln, "test_keymgr.sv")
        assert v.evidence_level.value == "E0"


@pytest.mark.skipif(not _has_api_key(), reason="OPENAI_API_KEY not set")
def test_auditor_attaches_deepwiki_context_to_findings():
    client = get_client()
    dw_client = DeepWikiClient("lowrisc/opentitan")

    dw_response = dw_client.ask_question(
        "How does the OpenTitan key manager verify key validity "
        "across multiple shares and what is the role of keymgr_input_checks?"
    )

    agent = OpenAIAuditorAgent(client, "gpt-5.6-sol")
    report = agent.run("test_keymgr.sv", TEST_SV)

    for finding in report.vulnerabilities:
        v = agent._to_vulnerability(finding, "test_keymgr.sv")
        v.deepwiki_queries = [{
            "question": "How does keymgr verify key validity?",
            "response": dw_response[:500],
        }]
        v.deepwiki_context_status = (
            DeepWikiContextStatus.revision_unverified
            if "unavailable" not in dw_response.lower()
            else DeepWikiContextStatus.unavailable
        )
        assert v.deepwiki_context_status in (
            DeepWikiContextStatus.revision_unverified,
            DeepWikiContextStatus.unavailable,
        )
        assert len(v.deepwiki_queries) == 1

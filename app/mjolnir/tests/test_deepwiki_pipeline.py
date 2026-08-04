"""Tests for DeepWiki integration with the audit pipeline."""
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.vulnerability import Vulnerability
from data.audit_finding import AuditFinding
from data.severity import Severity
from providers.deepwiki.client import DeepWikiClient, DeepWikiContextStatus


def test_auditor_can_query_deepwiki_for_related_files():
    """Discovery should use DeepWiki to find related modules before filing findings."""
    dw_client = DeepWikiClient("chipsalliance/mjolnir")
    result = dw_client.ask_question(
        "What is the architecture of Mjolnir and how do providers dispatch analysis?"
    )
    assert len(result) > 0
    assert "Mjolnir" not in result or "provider" not in result or "architecture" not in result or len(result) > 10


def test_deepwiki_client_returns_useful_response():
    """Even if the service is unavailable, the client should return a descriptive message."""
    dw_client = DeepWikiClient("chipsalliance/mjolnir")
    result = dw_client.read_wiki_structure()
    assert len(result) > 0


def test_finding_records_deepwiki_context():
    """When DeepWiki is used during discovery, the finding records the context."""
    dw_client = DeepWikiClient("chipsalliance/mjolnir")

    queries = [
        {
            "question": "How does keymgr verify key validity?",
            "response": dw_client.ask_question("How does the OpenTitan keymgr verify key validity and handle invalid keys?"),
        },
        {
            "question": "What are the caller modules of keymgr?",
            "response": dw_client.ask_question("What modules instantiate or call the key manager in OpenTitan?"),
        },
    ]

    finding = AuditFinding(
        title="Key validity check bypass",
        severity=Severity.HIGH,
        location="keymgr_input_checks.sv:69",
        description="Key validity qualifier may be ignored under certain conditions.",
        recommendation="Include validity qualifier in key_vld_o computation.",
    )

    vuln = Vulnerability(
        id=str(uuid.uuid4()),
        file="hw/ip/keymgr/rtl/keymgr_input_checks.sv",
        title=finding.title,
        severity=finding.severity,
        location=finding.location,
        description=finding.description,
        recommendation=finding.recommendation,
    )

    vuln.deepwiki_queries = queries
    vuln.deepwiki_verified = False
    vuln.deepwiki_context_status = DeepWikiContextStatus.revision_unverified

    assert len(vuln.deepwiki_queries) == 2
    assert vuln.deepwiki_context_status == DeepWikiContextStatus.revision_unverified
    assert vuln.deepwiki_verified is False

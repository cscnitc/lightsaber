"""Tests for DeepWiki context tracking in vulnerability findings."""
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.vulnerability import Vulnerability
from data.audit_finding import AuditFinding
from data.severity import Severity
from providers.deepwiki.client import DeepWikiContextStatus


def test_finding_tracks_deepwiki_context_status():
    finding = AuditFinding(
        title="Test",
        severity=Severity.MEDIUM,
        location="line 1",
        description="test",
        recommendation="test",
    )
    vuln = Vulnerability(
        id=str(uuid.uuid4()),
        file="test.sv",
        title=finding.title,
        severity=finding.severity,
        location=finding.location,
        description=finding.description,
        recommendation=finding.recommendation,
    )
    assert hasattr(vuln, "deepwiki_context_status")
    assert vuln.deepwiki_context_status == DeepWikiContextStatus.not_applicable


def test_finding_defaults_deepwiki_unavailable_when_verified_is_false():
    finding = AuditFinding(
        title="Test",
        severity=Severity.MEDIUM,
        location="line 1",
        description="test",
        recommendation="test",
    )
    vuln = Vulnerability(
        id=str(uuid.uuid4()),
        file="test.sv",
        title=finding.title,
        severity=finding.severity,
        location=finding.location,
        description=finding.description,
        recommendation=finding.recommendation,
    )
    assert vuln.deepwiki_verified is False


def test_finding_stores_deepwiki_query_history():
    finding = AuditFinding(
        title="Test",
        severity=Severity.MEDIUM,
        location="line 1",
        description="test",
        recommendation="test",
    )
    vuln = Vulnerability(
        id=str(uuid.uuid4()),
        file="test.sv",
        title=finding.title,
        severity=finding.severity,
        location=finding.location,
        description=finding.description,
        recommendation=finding.recommendation,
    )
    assert hasattr(vuln, "deepwiki_queries")
    assert vuln.deepwiki_queries == []

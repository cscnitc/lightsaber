"""Tests for evidence level in the data model."""
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.vulnerability import Vulnerability
from data.audit_finding import AuditFinding
from data.severity import Severity


def test_finding_has_evidence_level():
    finding = AuditFinding(
        title="Test",
        severity=Severity.MEDIUM,
        location="line 1",
        description="test desc",
        recommendation="test rec",
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
    assert hasattr(vuln, "evidence_level")
    assert vuln.evidence_level.value == "E0"


def test_finding_cannot_be_validated_without_evidence():
    finding = AuditFinding(
        title="Critical bug",
        severity=Severity.CRITICAL,
        location="line 42",
        description="Something serious",
        recommendation="Fix it",
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
    from data.evidence_level import EvidenceLevel
    vuln.evidence_level = EvidenceLevel.E0
    assert vuln.evidence_level == EvidenceLevel.E0
    vuln.evidence_level = EvidenceLevel.E2
    assert vuln.evidence_level == EvidenceLevel.E2
    assert vuln.evidence_level != EvidenceLevel.E4
    assert str(vuln.evidence_level.value) == "E2"

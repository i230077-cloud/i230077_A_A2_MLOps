"""Unit tests for secret redaction, deduplication, and schema validation."""

import pytest
from agent.sanitizer import redact_secrets, sanitize_violation, deduplicate_violations, clean_and_validate_violations
from agent.schema import Violation, AuditReport


def test_redact_aws_key():
    raw = "aws_key = 'AKIAIOSFODNN7EXAMPLE'"
    sanitized = redact_secrets(raw)
    assert "AKIAIOSFODNN7EXAMPLE" not in sanitized
    assert "[REDACTED_AWS_KEY]" in sanitized


def test_redact_openai_key():
    raw = "client = OpenAI(api_key='sk-1234567890abcdef1234567890abcdef')"
    sanitized = redact_secrets(raw)
    assert "sk-1234567890abcdef" not in sanitized
    assert "[REDACTED_OPENAI_KEY]" in sanitized


def test_redact_github_pat():
    raw = "Authorization: token ghp_123456789012345678901234567890123456"
    sanitized = redact_secrets(raw)
    assert "ghp_" not in sanitized
    assert "[REDACTED_GITHUB_PAT]" in sanitized


def test_sanitize_violation():
    v = Violation(
        rule_id="SEC-001",
        category="security",
        severity="critical",
        file="settings.py",
        line=10,
        description="Exposed key: AKIA1234567890EXAMPLE",
        evidence="Found secret key AKIA1234567890EXAMPLE in settings.py",
        recommendation="Use env var",
    )
    clean_v = sanitize_violation(v)
    assert "AKIA1234567890EXAMPLE" not in clean_v.description
    assert "AKIA1234567890EXAMPLE" not in clean_v.evidence
    assert "[REDACTED_AWS_KEY]" in clean_v.evidence


def test_deduplicate_violations():
    v1 = Violation(
        rule_id="SEC-001",
        category="security",
        severity="critical",
        file="config.py",
        line=12,
        description="Dup 1",
        evidence="Ev 1",
        recommendation="Rec 1",
    )
    v2 = Violation(
        rule_id="SEC-001",
        category="security",
        severity="critical",
        file="config.py",
        line=12,
        description="Dup 2",
        evidence="Ev 2",
        recommendation="Rec 2",
    )
    v3 = Violation(
        rule_id="CI-001",
        category="github actions / ci",
        severity="high",
        file=None,
        line=None,
        description="Different violation",
        evidence="No CI",
        recommendation="Add CI",
    )
    deduped = deduplicate_violations([v1, v2, v3])
    assert len(deduped) == 2
    assert deduped[0].rule_id == "SEC-001"
    assert deduped[1].rule_id == "CI-001"


def test_violation_normalization():
    # Category normalization and null line/file
    v = Violation(
        rule_id="CI-001",
        category="CI / Workflows",
        severity="HIGH",
        file="None",
        line="null",
        description="Test description",
        evidence="Test evidence",
        recommendation="Test recommendation",
    )
    assert v.category == "github actions / ci"
    assert v.severity == "high"
    assert v.file is None
    assert v.line is None


def test_audit_report_json_format():
    report = AuditReport(
        repository="https://github.com/example/repo",
        violations=[
            Violation(
                rule_id="SEC-001",
                category="security",
                severity="critical",
                file="app.py",
                line=5,
                description="Hardcoded credential",
                evidence="Key assigned directly",
                recommendation="Use secrets manager",
            )
        ],
    )
    json_str = report.model_dump_json_formatted()
    assert '"repository": "https://github.com/example/repo"' in json_str
    assert '"rule_id": "SEC-001"' in json_str
    assert '"severity": "critical"' in json_str

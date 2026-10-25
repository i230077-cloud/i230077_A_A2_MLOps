"""Secret redaction, evidence sanitization, and violation deduplication."""

import re
from typing import List, Optional
from agent.schema import Violation


SECRET_PATTERNS = [
    # AWS Access Key ID
    (re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE), "[REDACTED_AWS_KEY]"),
    # GitHub Personal Access Token (classic & fine-grained)
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "[REDACTED_GITHUB_PAT]"),
    (re.compile(r"github_pat_[a-zA-Z0-9_]{40,}"), "[REDACTED_GITHUB_PAT]"),
    (re.compile(r"gho_[a-zA-Z0-9]{36}"), "[REDACTED_GITHUB_OAUTH]"),
    # OpenAI API Key
    (re.compile(r"sk-[a-zA-Z0-9_-]{20,}"), "[REDACTED_OPENAI_KEY]"),
    # Google API Key / Firebase
    (re.compile(r"AIzaSy[a-zA-Z0-9_-]{33}"), "[REDACTED_GOOGLE_API_KEY]"),
    # Slack Tokens
    (re.compile(r"xox[baprs]-[0-9a-zA-Z-]{10,}"), "[REDACTED_SLACK_TOKEN]"),
    # Stripe Secret Keys
    (re.compile(r"(?:sk|rk)_live_[0-9a-zA-Z]{24,}"), "[REDACTED_STRIPE_KEY]"),
    # RSA / OpenSSH Private Keys
    (re.compile(r"-----BEGIN [A-Z\s]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z\s]+ PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    # Generic credential assignment patterns (avoiding already redacted tokens)
    (re.compile(r'''(?i)(password|passwd|secret|api_key|token|auth_token)\s*([:=])\s*['"](?!\[REDACTED_)([^'"]{6,})['"]'''), r'\1\2"[REDACTED_CREDENTIAL]"'),
    (re.compile(r'''(?i)(Bearer\s+)(?!\[REDACTED_)[a-zA-Z0-9_\-\.]{15,}'''), r'\1[REDACTED_BEARER_TOKEN]'),
]


def redact_secrets(text: Optional[str]) -> str:
    """Scrub raw secrets, credentials, and API keys from a text string."""
    if not text:
        return ""
    sanitized = text
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def sanitize_violation(v: Violation) -> Violation:
    """Sanitizes a single violation to ensure no raw secrets are retained."""
    sanitized_evidence = redact_secrets(v.evidence)
    sanitized_description = redact_secrets(v.description)
    return Violation(
        rule_id=v.rule_id,
        category=v.category,
        severity=v.severity,
        file=v.file,
        line=v.line,
        description=sanitized_description,
        evidence=sanitized_evidence,
        recommendation=v.recommendation,
    )


def deduplicate_violations(violations: List[Violation]) -> List[Violation]:
    """Removes duplicate violations based on rule_id, file, and line."""
    seen = set()
    deduped = []
    for v in violations:
        # Create a unique signature
        norm_file = (v.file or "").strip().lower()
        key = (v.rule_id.strip().upper(), norm_file, v.line)
        if key not in seen:
            seen.add(key)
            deduped.append(v)
    return deduped


def clean_and_validate_violations(violations: List[Violation]) -> List[Violation]:
    """Applies sanitization, validation, and deduplication across all violations."""
    cleaned = [sanitize_violation(v) for v in violations]
    return deduplicate_violations(cleaned)

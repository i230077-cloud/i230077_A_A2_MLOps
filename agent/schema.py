"""Data models and schemas for the DevOps Repository Auditing Agent."""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator


SeverityType = Literal["critical", "high", "medium", "low"]

VALID_CATEGORIES = {
    "repository hygiene",
    "dependency management",
    "code quality",
    "testing",
    "github actions / ci",
    "security",
    "configuration",
    "collaboration",
    "build and release",
}


class Violation(BaseModel):
    """Represents a single DevOps best-practice violation."""
    rule_id: str = Field(..., description="Unique rule identifier (e.g., SEC-001, CI-002)")
    category: str = Field(..., description="DevOps category (e.g., security, testing)")
    severity: SeverityType = Field(..., description="Violation severity: critical, high, medium, low")
    file: Optional[str] = Field(None, description="Path to offending file, or None/null if not applicable")
    line: Optional[int] = Field(None, description="Line number of violation, or None/null if not applicable")
    description: str = Field(..., description="Brief description of the violation")
    evidence: str = Field(..., description="Concrete observed evidence; never include actual secret values")
    recommendation: str = Field(..., description="Actionable recommendation to remediate the violation")

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, v: str) -> str:
        if isinstance(v, str):
            v_lower = v.strip().lower()
            if v_lower in {"critical", "high", "medium", "low"}:
                return v_lower
        raise ValueError(f"Severity must be one of: critical, high, medium, low (got '{v}')")

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v: str) -> str:
        if isinstance(v, str):
            v_lower = v.strip().lower()
            # Normalize common synonyms
            if "hygiene" in v_lower:
                return "repository hygiene"
            if "depend" in v_lower:
                return "dependency management"
            if "quality" in v_lower or "lint" in v_lower:
                return "code quality"
            if "test" in v_lower:
                return "testing"
            if "action" in v_lower or "ci" in v_lower or "workflow" in v_lower:
                return "github actions / ci"
            if "sec" in v_lower:
                return "security"
            if "config" in v_lower or "env" in v_lower:
                return "configuration"
            if "collab" in v_lower or "pr" in v_lower or "review" in v_lower:
                return "collaboration"
            if "build" in v_lower or "release" in v_lower or "deploy" in v_lower:
                return "build and release"
            return v_lower
        return v

    @field_validator("file", mode="before")
    @classmethod
    def normalize_file(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_str = str(v).strip()
        if not v_str or v_str.lower() in {"none", "null", "n/a", "na"}:
            return None
        # Normalize backslashes to forward slashes
        return v_str.replace("\\", "/")

    @field_validator("line", mode="before")
    @classmethod
    def normalize_line(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        if isinstance(v, str):
            v_str = v.strip().lower()
            if not v_str or v_str in {"none", "null", "n/a", "na"}:
                return None
            try:
                return int(v_str)
            except ValueError:
                return None
        if isinstance(v, (int, float)):
            return int(v) if v > 0 else None
        return None


class AuditReport(BaseModel):
    """Top-level machine-readable JSON report output contract."""
    repository: str = Field(..., description="URL of the inspected repository")
    violations: List[Violation] = Field(default_factory=list, description="List of identified violations")

    def model_dump_json_formatted(self) -> str:
        """Serializes report to formatted JSON matching specification."""
        import json
        return json.dumps(self.model_dump(), indent=2)

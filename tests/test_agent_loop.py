"""Unit tests for the autonomous agent reasoning loop and tool dispatch."""

import subprocess
import pytest
from pathlib import Path

from agent.core import DevOpsAuditAgent
from agent.providers import MockClient
from agent.schema import AuditReport


@pytest.fixture
def mock_repo_for_loop(tmp_path):
    repo_dir = tmp_path / "agent_test_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Auditor"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "auditor@example.com"], cwd=str(repo_dir), check=True, capture_output=True)

    (repo_dir / "README.md").write_text("# Project\n")
    (repo_dir / "secrets.env").write_text("DATABASE_PASSWORD=SuperSecret123\n")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Commit with env file"], cwd=str(repo_dir), check=True, capture_output=True)
    return repo_dir


def test_agent_loop_execution(mock_repo_for_loop):
    scripted_turns = [
        # Turn 1: Call list_files
        {
            "thought": "I will inspect repository files first to discover structure.",
            "action": "call_tool",
            "tool_name": "list_files",
            "arguments": {"path": ""},
        },
        # Turn 2: Call search_code for secrets
        {
            "thought": "I noticed secrets.env, now searching code for password patterns.",
            "action": "call_tool",
            "tool_name": "search_code",
            "arguments": {"pattern": "DATABASE_PASSWORD"},
        },
        # Turn 3: Complete audit and emit report
        {
            "thought": "Inspection complete. Formulating final audit report.",
            "action": "finish",
            "report": {
                "repository": "https://github.com/example/agent-repo",
                "violations": [
                    {
                        "rule_id": "SEC-002",
                        "category": "security",
                        "severity": "critical",
                        "file": "secrets.env",
                        "line": 1,
                        "description": "Committed sensitive environment file",
                        "evidence": "File contains DATABASE_PASSWORD=[REDACTED_CREDENTIAL]",
                        "recommendation": "Remove file from tracking and use .env.example",
                    }
                ],
            },
        },
    ]

    mock_client = MockClient(scripted_steps=scripted_turns)
    captured_steps = []

    def on_step(step):
        captured_steps.append(step)

    agent = DevOpsAuditAgent(
        llm_client=mock_client,
        max_iterations=5,
        on_step_callback=on_step,
    )

    report = agent.audit("https://github.com/example/agent-repo", mock_repo_for_loop)

    assert isinstance(report, AuditReport)
    assert report.repository == "https://github.com/example/agent-repo"
    assert len(report.violations) == 1
    assert report.violations[0].rule_id == "SEC-002"
    assert report.violations[0].severity == "critical"
    assert len(captured_steps) == 3
    assert captured_steps[0]["tool_name"] == "list_files"
    assert captured_steps[1]["tool_name"] == "search_code"


def test_agent_graceful_tool_error(mock_repo_for_loop):
    # Tool call with invalid arguments shouldn't crash agent
    scripted_turns = [
        {
            "thought": "Calling non-existent tool.",
            "action": "call_tool",
            "tool_name": "invalid_tool_name",
            "arguments": {},
        },
        {
            "thought": "Recovering and finishing.",
            "action": "finish",
            "report": {
                "repository": "https://github.com/example/agent-repo",
                "violations": [],
            },
        },
    ]

    mock_client = MockClient(scripted_steps=scripted_turns)
    agent = DevOpsAuditAgent(llm_client=mock_client, max_iterations=3)
    report = agent.audit("https://github.com/example/agent-repo", mock_repo_for_loop)
    assert isinstance(report, AuditReport)
    assert len(report.violations) == 0

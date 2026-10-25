"""End-to-end integration tests for the CLI entry point."""

import json
import subprocess
import sys
from pathlib import Path
import pytest


@pytest.fixture
def test_repo_dir(tmp_path):
    repo_dir = tmp_path / "cli_test_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Auditor"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "auditor@example.com"], cwd=str(repo_dir), check=True, capture_output=True)
    (repo_dir / "README.md").write_text("# Healthy Project\nClean repository structure.\n")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial clean commit"], cwd=str(repo_dir), check=True, capture_output=True)
    return repo_dir


def test_cli_mock_run(test_repo_dir, tmp_path):
    output_json = tmp_path / "report.json"
    cmd = [
        sys.executable,
        "agent.py",
        "--repo", str(test_repo_dir),
        "--output", str(output_json),
        "--mock",
        "--quiet",
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"CLI failed with stderr: {res.stderr}"

    assert output_json.exists(), "Output JSON file was not created"
    data = json.loads(output_json.read_text(encoding="utf-8"))

    assert "repository" in data
    assert "violations" in data
    assert isinstance(data["violations"], list)


def test_cli_missing_required_args():
    cmd = [sys.executable, "agent.py"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode != 0
    assert "error" in res.stderr.lower() or "required" in res.stderr.lower()

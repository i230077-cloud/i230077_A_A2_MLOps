"""Unit tests for inspection tools."""

import os
import subprocess
import tempfile
from pathlib import Path
import pytest

from tools import RepoInspector


@pytest.fixture
def mock_repo(tmp_path):
    """Creates a temporary initialized git repository with sample files."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # Initialize git
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Auditor"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "auditor@example.com"], cwd=str(repo_dir), check=True, capture_output=True)

    # Create files
    (repo_dir / "README.md").write_text("# Test Repo\nDevOps audit test repository.\n")
    (repo_dir / "config.py").write_text("import os\nAPI_KEY = 'AKIA1234567890EXAMPLE'\nDEBUG = True\n")
    
    src_dir = repo_dir / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("print('Hello World')\nLOCAL_PATH = 'C:\\Users\\admin\\data'\n")

    # Workflows
    wf_dir = repo_dir / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    ci_yaml = """name: CI
on:
  pull_request_target:
permissions: write-all
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: thirdparty/unpinned-action@master
      - name: Run tests
        run: pytest
        continue-on-error: true
"""
    (wf_dir / "ci.yml").write_text(ci_yaml)

    # Dependencies
    (repo_dir / "Pipfile").write_text("[packages]\nrequests = '*'\n")

    # Commit files
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial test commit with sample defects"], cwd=str(repo_dir), check=True, capture_output=True)

    return repo_dir


def test_list_files(mock_repo):
    inspector = RepoInspector(mock_repo)
    res = inspector.list_files()
    assert "files" in res
    assert res["total_files"] >= 4
    paths = [f["path"] for f in res["files"]]
    assert "README.md" in paths
    assert "config.py" in paths
    assert ".github/workflows/ci.yml" in paths


def test_list_files_pattern_and_depth(mock_repo):
    inspector = RepoInspector(mock_repo)
    res = inspector.list_files(pattern="*.py")
    assert all(f["path"].endswith(".py") for f in res["files"])
    paths = [f["path"] for f in res["files"]]
    assert "config.py" in paths
    assert "src/app.py" in paths


def test_read_file(mock_repo):
    inspector = RepoInspector(mock_repo)
    res = inspector.read_file("README.md")
    assert "content" in res
    assert "# Test Repo" in res["content"]
    assert res["total_lines"] == 2


def test_read_file_slicing(mock_repo):
    inspector = RepoInspector(mock_repo)
    res = inspector.read_file("config.py", start_line=2, end_line=2)
    assert res["start_line"] == 2
    assert res["end_line"] == 2
    assert "API_KEY" in res["content"]
    # Secret must be redacted!
    assert "AKIA1234567890EXAMPLE" not in res["content"]
    assert "[REDACTED_AWS_KEY]" in res["content"]


def test_read_file_path_traversal_protection(mock_repo):
    inspector = RepoInspector(mock_repo)
    res = inspector.read_file("../../secret.txt")
    assert "error" in res
    assert "escapes repository boundary" in res["error"]


def test_search_code(mock_repo):
    inspector = RepoInspector(mock_repo)
    res = inspector.search_code("API_KEY")
    assert res["total_matches"] >= 1
    assert res["matches"][0]["file"] == "config.py"
    # Content line must be sanitized
    assert "AKIA1234567890EXAMPLE" not in res["matches"][0]["matched_line"]


def test_search_code_regex(mock_repo):
    inspector = RepoInspector(mock_repo)
    res = inspector.search_code(r"Users[/\\]admin", is_regex=True)
    assert res["total_matches"] >= 1
    assert "src/app.py" in res["matches"][0]["file"]


def test_git_log(mock_repo):
    inspector = RepoInspector(mock_repo)
    res = inspector.git_log(max_count=5)
    assert "commits" in res
    assert len(res["commits"]) >= 1
    assert res["commits"][0]["author_name"] == "Test Auditor"
    assert "Initial test commit" in res["commits"][0]["subject"]


def test_inspect_ci_workflows(mock_repo):
    inspector = RepoInspector(mock_repo)
    res = inspector.inspect_ci_workflows()
    assert res["has_ci"] is True
    assert res["workflows_found"] == 1
    wf = res["workflows"][0]
    assert wf["has_pull_request_target"] is True
    assert wf["has_write_all_permissions"] is True
    assert wf["runs_tests"] is True
    assert len(wf["unpinned_external_actions"]) > 0
    assert len(wf["continue_on_error_steps"]) > 0


def test_check_dependencies(mock_repo):
    inspector = RepoInspector(mock_repo)
    res = inspector.check_dependencies()
    assert res["python"]["has_pipfile"] is True
    assert res["python"]["has_pipfile_lock"] is False
    assert "missing Pipfile.lock" in res["python"]["lockfile_issue"]

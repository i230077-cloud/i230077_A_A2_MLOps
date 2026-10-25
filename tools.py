"""Inspection tool implementations for repository auditing."""

import fnmatch
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from agent.sanitizer import redact_secrets


class RepoInspector:
    """Manages and executes inspection tools safely within a cloned repository."""

    def __init__(self, repo_dir: Path):
        self.repo_dir = Path(repo_dir).resolve()
        if not self.repo_dir.is_dir():
            raise ValueError(f"Repository directory does not exist: {repo_dir}")

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """Resolves a relative path and verifies it does not escape repo_dir."""
        # Normalize and remove leading slashes or drive letters
        cleaned = relative_path.strip().lstrip("/\\")
        target = (self.repo_dir / cleaned).resolve()
        try:
            target.relative_to(self.repo_dir)
        except ValueError:
            raise PermissionError(f"Access denied: path '{relative_path}' escapes repository boundary.")
        return target

    def list_files(self, path: str = "", max_depth: int = 5, pattern: str = "*") -> Dict[str, Any]:
        """Discover repository files and directory structure.
        
        Args:
            path: Relative directory path inside the repo to list (defaults to root).
            max_depth: Maximum directory recursion depth (default: 5).
            pattern: Glob filter for filenames (e.g., '*.py', '*.yml').
        """
        try:
            target_dir = self._resolve_safe_path(path)
            if not target_dir.exists():
                return {"error": f"Directory not found: {path}"}
            if not target_dir.is_dir():
                return {"error": f"Path is not a directory: {path}"}

            results: List[Dict[str, Any]] = []
            base_parts_len = len(target_dir.parts)

            for root, dirs, files in os.walk(target_dir):
                current_depth = len(Path(root).parts) - base_parts_len
                if current_depth >= max_depth:
                    dirs.clear()  # Do not recurse further
                    continue

                # Filter out .git internal directory
                if ".git" in dirs:
                    dirs.remove(".git")

                for file in files:
                    if pattern == "*" or fnmatch.fnmatch(file, pattern):
                        full_file_path = Path(root) / file
                        rel_path = str(full_file_path.relative_to(self.repo_dir)).replace("\\", "/")
                        size_bytes = full_file_path.stat().st_size if full_file_path.exists() else 0
                        results.append({
                            "path": rel_path,
                            "size_bytes": size_bytes,
                        })

            return {
                "total_files": len(results),
                "files": results[:500],  # Bound total returned to avoid exceeding context
                "truncated": len(results) > 500,
            }
        except Exception as e:
            return {"error": str(e)}

    def read_file(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, Any]:
        """Inspect relevant source or configuration file content.
        
        Args:
            path: Relative path to the file within the repository.
            start_line: 1-indexed optional starting line number.
            end_line: 1-indexed optional ending line number.
        """
        try:
            target_file = self._resolve_safe_path(path)
            if not target_file.exists():
                return {"error": f"File does not exist: {path}"}
            if not target_file.is_file():
                return {"error": f"Path is a directory, not a file: {path}"}

            # Avoid reading very large binary files
            if target_file.stat().st_size > 2 * 1024 * 1024:
                return {"error": f"File too large to inspect (>2MB): {path}"}

            try:
                content = target_file.read_text(encoding="utf-8", errors="replace")
            except Exception as read_err:
                return {"error": f"Failed to read file: {read_err}"}

            lines = content.splitlines()
            total_lines = len(lines)

            s_idx = max(0, (start_line - 1)) if start_line is not None else 0
            e_idx = min(total_lines, end_line) if end_line is not None else total_lines

            sliced_lines = lines[s_idx:e_idx]
            numbered_content = [
                f"{i + 1:4d} | {line}"
                for i, line in enumerate(sliced_lines, start=s_idx)
            ]

            return {
                "path": str(target_file.relative_to(self.repo_dir)).replace("\\", "/"),
                "total_lines": total_lines,
                "start_line": s_idx + 1,
                "end_line": min(e_idx, total_lines),
                "content": redact_secrets("\n".join(numbered_content)),
            }
        except Exception as e:
            return {"error": str(e)}

    def search_code(self, pattern: str, file_pattern: str = "*", is_regex: bool = False) -> Dict[str, Any]:
        """Search for suspicious patterns across repository code and configuration.
        
        Args:
            pattern: Search string or regex pattern.
            file_pattern: Glob pattern to filter target files (e.g., '*.py', '*.yml', '*.env*').
            is_regex: Whether pattern should be evaluated as a regular expression.
        """
        try:
            if not pattern:
                return {"error": "Search pattern cannot be empty."}

            if is_regex:
                try:
                    compiled_re = re.compile(pattern, re.IGNORECASE)
                except re.error as re_err:
                    return {"error": f"Invalid regular expression: {re_err}"}
            else:
                compiled_re = re.compile(re.escape(pattern), re.IGNORECASE)

            matches: List[Dict[str, Any]] = []

            for root, dirs, files in os.walk(self.repo_dir):
                if ".git" in dirs:
                    dirs.remove(".git")
                if "__pycache__" in dirs:
                    dirs.remove("__pycache__")

                for file in files:
                    if file_pattern == "*" or fnmatch.fnmatch(file, file_pattern):
                        full_path = Path(root) / file
                        rel_path = str(full_path.relative_to(self.repo_dir)).replace("\\", "/")

                        # Skip large or binary files
                        if full_path.stat().st_size > 1024 * 1024:
                            continue

                        try:
                            lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
                            for line_num, line_text in enumerate(lines, start=1):
                                if compiled_re.search(line_text):
                                    matches.append({
                                        "file": rel_path,
                                        "line": line_num,
                                        "matched_line": redact_secrets(line_text.strip()),
                                    })
                                    if len(matches) >= 100:
                                        break
                        except Exception:
                            continue

                    if len(matches) >= 100:
                        break
                if len(matches) >= 100:
                    break

            return {
                "pattern": pattern,
                "total_matches": len(matches),
                "matches": matches,
                "truncated": len(matches) >= 100,
            }
        except Exception as e:
            return {"error": str(e)}

    def git_log(self, max_count: int = 20, path: Optional[str] = None) -> Dict[str, Any]:
        """Inspect repository commit history for commit hygiene, unverified merges, or sensitive messages.
        
        Args:
            max_count: Maximum number of commits to retrieve (default: 20).
            path: Optional file or directory path to filter commit history.
        """
        try:
            cmd = [
                "git", "log",
                f"-n{max_count}",
                "--pretty=format:%H|%an|%ae|%ad|%s",
                "--date=iso",
            ]
            if path:
                safe_path = self._resolve_safe_path(path)
                cmd.extend(["--", str(safe_path.relative_to(self.repo_dir))])

            res = subprocess.run(
                cmd,
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=15,
                check=False
            )
            if res.returncode != 0:
                return {"error": f"git log failed: {res.stderr.strip()}"}

            commits: List[Dict[str, Any]] = []
            for line in res.stdout.strip().splitlines():
                if not line.strip():
                    continue
                parts = line.split("|", 4)
                if len(parts) == 5:
                    commits.append({
                        "commit_hash": parts[0][:8],
                        "author_name": parts[1],
                        "author_email": parts[2],
                        "date": parts[3],
                        "subject": redact_secrets(parts[4]),
                    })

            return {
                "total_commits_inspected": len(commits),
                "commits": commits,
            }
        except Exception as e:
            return {"error": str(e)}

    def git_status(self) -> Dict[str, Any]:
        """Inspect repository working tree status and check for untracked/ignored file hygiene."""
        try:
            cmd = ["git", "status", "--porcelain", "--ignored"]
            res = subprocess.run(
                cmd,
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            if res.returncode != 0:
                return {"error": f"git status failed: {res.stderr.strip()}"}

            entries = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            return {
                "clean": len(entries) == 0,
                "entries": entries[:50],
            }
        except Exception as e:
            return {"error": str(e)}

    def inspect_ci_workflows(self) -> Dict[str, Any]:
        """Specialized analyzer for GitHub Actions workflows (.github/workflows/*.yml).
        Inspects triggers, permissions, checkout references, and gates.
        """
        try:
            workflows_dir = self.repo_dir / ".github" / "workflows"
            if not workflows_dir.exists() or not workflows_dir.is_dir():
                return {
                    "has_ci": False,
                    "workflows_found": 0,
                    "workflows": [],
                    "summary": "No GitHub Actions workflows directory found (.github/workflows)."
                }

            workflow_files = list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))
            if not workflow_files:
                return {
                    "has_ci": False,
                    "workflows_found": 0,
                    "workflows": [],
                    "summary": "Workflows directory exists but contains no YAML workflow files."
                }

            workflow_reports: List[Dict[str, Any]] = []

            for wf_file in workflow_files:
                rel_path = str(wf_file.relative_to(self.repo_dir)).replace("\\", "/")
                content = wf_file.read_text(encoding="utf-8", errors="replace")
                
                try:
                    data = yaml.safe_load(content) or {}
                except Exception as parse_err:
                    workflow_reports.append({
                        "file": rel_path,
                        "error": f"YAML syntax error: {parse_err}",
                    })
                    continue

                # Analyze triggers
                on_trigger = data.get("on") or data.get(True)  # In YAML 'on' can parse as True
                has_pull_request_target = False
                if isinstance(on_trigger, str) and on_trigger == "pull_request_target":
                    has_pull_request_target = True
                elif isinstance(on_trigger, list) and "pull_request_target" in on_trigger:
                    has_pull_request_target = True
                elif isinstance(on_trigger, dict) and "pull_request_target" in on_trigger:
                    has_pull_request_target = True

                # Analyze permissions
                permissions = data.get("permissions")
                has_write_all = permissions == "write-all"

                # Analyze jobs and steps
                jobs = data.get("jobs", {})
                job_names = list(jobs.keys()) if isinstance(jobs, dict) else []
                tests_found = False
                unpinned_actions = []
                continue_on_error_steps = []

                if isinstance(jobs, dict):
                    for j_name, j_data in jobs.items():
                        if not isinstance(j_data, dict):
                            continue
                        steps = j_data.get("steps", [])
                        if isinstance(steps, list):
                            for step in steps:
                                if not isinstance(step, dict):
                                    continue
                                uses = step.get("uses", "")
                                run = step.get("run", "")
                                # Check for tests
                                if any(t in run.lower() for t in ["pytest", "npm test", "go test", "cargo test", "python -m unittest"]):
                                    tests_found = True
                                # Check for continue-on-error
                                if step.get("continue-on-error") is True or "|| true" in run:
                                    continue_on_error_steps.append({
                                        "job": j_name,
                                        "step": step.get("name") or run[:40],
                                    })
                                # Check unpinned 3rd-party actions
                                if uses and "/" in uses and not uses.startswith("actions/"):
                                    parts = uses.split("@")
                                    if len(parts) == 2:
                                        ref = parts[1]
                                        # Not a 40-character commit SHA
                                        if not (len(ref) == 40 and all(c in "0123456789abcdefABCDEF" for c in ref)):
                                            unpinned_actions.append(uses)

                workflow_reports.append({
                    "file": rel_path,
                    "triggers": str(on_trigger),
                    "has_pull_request_target": has_pull_request_target,
                    "has_write_all_permissions": has_write_all,
                    "jobs": job_names,
                    "runs_tests": tests_found,
                    "unpinned_external_actions": unpinned_actions[:10],
                    "continue_on_error_steps": continue_on_error_steps,
                })

            return {
                "has_ci": True,
                "workflows_found": len(workflow_reports),
                "workflows": workflow_reports,
            }
        except Exception as e:
            return {"error": str(e)}

    def check_dependencies(self) -> Dict[str, Any]:
        """Inspects dependency declarations and lockfiles across common package managers."""
        findings: Dict[str, Any] = {
            "python": {},
            "javascript": {},
            "rust": {},
            "go": {},
        }

        # Python checks
        req_txt = self.repo_dir / "requirements.txt"
        pyproject = self.repo_dir / "pyproject.toml"
        pipfile = self.repo_dir / "Pipfile"
        pipfile_lock = self.repo_dir / "Pipfile.lock"
        poetry_lock = self.repo_dir / "poetry.lock"
        uv_lock = self.repo_dir / "uv.lock"

        findings["python"]["has_requirements_txt"] = req_txt.exists()
        findings["python"]["has_pyproject"] = pyproject.exists()
        findings["python"]["has_pipfile"] = pipfile.exists()
        findings["python"]["has_pipfile_lock"] = pipfile_lock.exists()
        findings["python"]["has_poetry_lock"] = poetry_lock.exists()
        findings["python"]["has_uv_lock"] = uv_lock.exists()

        if pipfile.exists() and not pipfile_lock.exists():
            findings["python"]["lockfile_issue"] = "Pipfile present but missing Pipfile.lock"

        if pyproject.exists():
            content = pyproject.read_text(encoding="utf-8", errors="replace")
            if "[tool.poetry]" in content and not poetry_lock.exists():
                findings["python"]["lockfile_issue"] = "Poetry configured in pyproject.toml but missing poetry.lock"

        # Check for unpinned deps in requirements.txt
        if req_txt.exists():
            req_lines = [l.strip() for l in req_txt.read_text(encoding="utf-8", errors="replace").splitlines()]
            unpinned = [l for l in req_lines if l and not l.startswith("#") and not any(op in l for op in ["==", ">=", "<=", "~=", "!="])]
            findings["python"]["unpinned_requirements_count"] = len(unpinned)
            findings["python"]["sample_unpinned"] = unpinned[:5]

        # JavaScript checks
        pkg_json = self.repo_dir / "package.json"
        pkg_lock = self.repo_dir / "package-lock.json"
        yarn_lock = self.repo_dir / "yarn.lock"
        pnpm_lock = self.repo_dir / "pnpm-lock.yaml"

        findings["javascript"]["has_package_json"] = pkg_json.exists()
        findings["javascript"]["has_lockfile"] = pkg_lock.exists() or yarn_lock.exists() or pnpm_lock.exists()
        if pkg_json.exists() and not findings["javascript"]["has_lockfile"]:
            findings["javascript"]["lockfile_issue"] = "package.json present but no lockfile found (package-lock.json, yarn.lock, or pnpm-lock.yaml)"

        return findings


# JSON Schema Definitions for Tool Calling (compatible with Google GenAI / OpenAI function calling)
TOOL_DEFINITIONS = [
    {
        "name": "list_files",
        "description": "Discover repository files and directory structure. Call this first to observe the layout.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative directory path inside repository to inspect (default is root '').",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum directory recursion depth (default 5).",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files, e.g. '*.py', '*.yml', '*.json'.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": "Inspect contents of a source code, workflow, or configuration file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of file inside repository.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Optional 1-indexed start line number.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Optional 1-indexed end line number.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_code",
        "description": "Search for suspicious patterns across repository code and configs (e.g. secrets, machine paths, disabled linters).",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Text or regex search pattern.",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob filter for target files (e.g., '*.py', '*.yml', '*.env*').",
                },
                "is_regex": {
                    "type": "boolean",
                    "description": "Set to true if pattern is a regular expression.",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "git_log",
        "description": "Inspect commit history for commit hygiene, unverified merges, or sensitive messages.",
        "parameters": {
            "type": "object",
            "properties": {
                "max_count": {
                    "type": "integer",
                    "description": "Maximum number of recent commits to fetch (default: 20).",
                },
                "path": {
                    "type": "string",
                    "description": "Optional path to filter commits for a specific file or directory.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "git_status",
        "description": "Inspect git status for tracked temporary files, untracked generated artifacts, or dirty state.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "inspect_ci_workflows",
        "description": "Specialized tool to inspect GitHub Actions CI/CD workflows for triggers (pull_request_target), permissions (write-all), unpinned actions, and missing test execution.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "check_dependencies",
        "description": "Specialized tool to cross-check dependency declarations, missing lockfiles, and unpinned dependencies.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

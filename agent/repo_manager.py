"""Repository lifecycle management: isolated cloning, path safety, and cleanup."""

import os
import stat
import shutil
import subprocess
import tempfile
import urllib.parse
from pathlib import Path
from typing import Optional


def _remove_readonly(func, path, exc_info):
    """Error handler for shutil.rmtree on Windows when encountering read-only files."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


class ClonedRepository:
    """Context manager representing an isolated cloned repository."""

    def __init__(self, repo_url: str, shallow_depth: int = 50, keep_on_error: bool = False):
        self.repo_url = repo_url.strip()
        self.shallow_depth = shallow_depth
        self.keep_on_error = keep_on_error
        self.temp_dir: Optional[str] = None
        self.repo_dir: Optional[Path] = None

    def __enter__(self) -> Path:
        # Check if repo_url is an existing local directory (for local testing/fixtures)
        candidate_path = Path(self.repo_url)
        if candidate_path.is_dir() and (candidate_path / ".git").exists():
            # Create a clean isolated copy to ensure we NEVER modify the original repo
            self.temp_dir = tempfile.mkdtemp(prefix="devops_audit_")
            dest_dir = Path(self.temp_dir) / "repo"
            shutil.copytree(candidate_path, dest_dir, symlinks=True, ignore_dangling_symlinks=True)
            self.repo_dir = dest_dir
            return self.repo_dir

        # Otherwise clone via Git
        self.temp_dir = tempfile.mkdtemp(prefix="devops_audit_")
        dest_dir = Path(self.temp_dir) / "repo"

        # Validate git url format
        if not (self.repo_url.startswith("http://") or 
                self.repo_url.startswith("https://") or 
                self.repo_url.startswith("git@") or 
                self.repo_url.startswith("ssh://")):
            raise ValueError(f"Invalid repository URL: {self.repo_url}. Expected public Git/GitHub URL.")

        cmd = [
            "git", "clone",
            "--depth", str(self.shallow_depth),
            self.repo_url,
            str(dest_dir)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                check=False
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to clone repository '{self.repo_url}'. "
                    f"Git error: {result.stderr.strip() or result.stdout.strip()}"
                )
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Cloning timed out for repository: {self.repo_url}")
        except FileNotFoundError:
            raise RuntimeError("Git executable not found. Please ensure 'git' is installed and in PATH.")

        self.repo_dir = dest_dir
        return self.repo_dir

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_dir and os.path.exists(self.temp_dir):
            if exc_type is not None and self.keep_on_error:
                return False
            try:
                shutil.rmtree(self.temp_dir, onerror=_remove_readonly)
            except Exception:
                pass
        return False

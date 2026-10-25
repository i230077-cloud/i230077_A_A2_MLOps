"""DevOps Audit Rules Catalog and Evidence Standards."""

from typing import Dict, Any

# Canonical Rule Definitions across the 9 DevOps Inspection Areas
DEVOPS_RULES: Dict[str, Dict[str, Any]] = {
    # 1. Repository Hygiene
    "HYG-001": {
        "name": "Missing Documentation / README",
        "category": "repository hygiene",
        "default_severity": "medium",
        "description": "Repository lacks a README or setup documentation explaining project purpose and execution.",
        "evidence_guidance": "Absence of README.md, README.rst, or README.txt in repository root.",
        "recommendation": "Add a comprehensive README.md describing the project, installation, and usage."
    },
    "HYG-002": {
        "name": "Missing or Inadequate .gitignore",
        "category": "repository hygiene",
        "default_severity": "medium",
        "description": "Repository lacks a .gitignore or fails to exclude standard language build/cache artifacts.",
        "evidence_guidance": "No .gitignore present, or .gitignore missing common ignore patterns for project tech stack.",
        "recommendation": "Add or update .gitignore with appropriate patterns for the project's language and tools."
    },
    "HYG-003": {
        "name": "Tracked Temporary or Generated Files",
        "category": "repository hygiene",
        "default_severity": "high",
        "description": "Temporary, cache, or compiled build artifacts are tracked in the git repository.",
        "evidence_guidance": "Committed __pycache__, *.pyc, .DS_Store, build/, dist/, node_modules/, or .env files.",
        "recommendation": "Untrack generated/temporary files using 'git rm --cached' and add them to .gitignore."
    },

    # 2. Dependency Management
    "DEP-001": {
        "name": "Missing Required Lockfile",
        "category": "dependency management",
        "default_severity": "high",
        "description": "Dependency specification is present without a corresponding lockfile, risking non-deterministic builds.",
        "evidence_guidance": "Poetry project without poetry.lock, Pipenv without Pipfile.lock, npm package.json without package-lock.json/yarn.lock/pnpm-lock.yaml. Note: Plain requirements.txt without lockfile tooling is not necessarily an error unless pip-tools/uv is used.",
        "recommendation": "Generate and commit a deterministic dependency lockfile to ensure reproducible environments."
    },
    "DEP-002": {
        "name": "Unpinned or Weak Version Constraints",
        "category": "dependency management",
        "default_severity": "medium",
        "description": "Dependencies declared with wildcard constraints (*) or completely unpinned in production specifications.",
        "evidence_guidance": "Presence of bare package names or wildcard (*) versions in dependency manifests without lockfiles.",
        "recommendation": "Pin dependency versions or specify explicit version bounds (e.g. ~= or ==) in dependency specifications."
    },
    "DEP-003": {
        "name": "Inconsistent Dependency Specifications",
        "category": "dependency management",
        "default_severity": "high",
        "description": "Multiple conflicting dependency specification systems present with inconsistent package versions.",
        "evidence_guidance": "Both Pipfile and requirements.txt present with divergent package versions or outdated locks.",
        "recommendation": "Consolidate to a single source of truth for dependencies and maintain synchronized specifications."
    },

    # 3. Code Quality
    "QUAL-001": {
        "name": "Missing Linting or Code Formatting Configuration",
        "category": "code quality",
        "default_severity": "medium",
        "description": "Repository lacks static analysis, linting, or formatting configuration.",
        "evidence_guidance": "Absence of ruff, flake8, black, eslint, prettier, or linter configuration in pyproject.toml/setup.cfg.",
        "recommendation": "Configure a modern linter/formatter (such as ruff or flake8) to enforce code consistency."
    },
    "QUAL-002": {
        "name": "Obvious Code Quality or Maintainability Defects",
        "category": "code quality",
        "default_severity": "medium",
        "description": "Widespread linting violations, syntax anomalies, or blatant maintainability problems.",
        "evidence_guidance": "Failing syntax checks, disabled lint checks repo-wide (# noqa on everything), or unhandled errors.",
        "recommendation": "Resolve static analysis errors and enforce lint checks as automated pre-commit or CI gates."
    },

    # 4. Testing
    "TEST-001": {
        "name": "Missing Automated Test Suite",
        "category": "testing",
        "default_severity": "high",
        "description": "Repository contains no automated unit or integration tests.",
        "evidence_guidance": "Absence of test files, test directories (tests/, test/), or test framework configurations.",
        "recommendation": "Implement automated tests using pytest, unittest, or appropriate testing framework."
    },
    "TEST-002": {
        "name": "Tests Not Executed in CI Pipeline",
        "category": "testing",
        "default_severity": "high",
        "description": "Test suite exists in the codebase but is never invoked within the CI workflow.",
        "evidence_guidance": "CI workflows (.github/workflows) exist but contain no step running pytest, npm test, or test runner.",
        "recommendation": "Add an automated test step to CI workflows that triggers on all pull requests and main pushes."
    },
    "TEST-003": {
        "name": "Ineffective or Disabled Test Gates",
        "category": "testing",
        "default_severity": "high",
        "description": "Test executions in CI are configured to ignore failures, bypassing quality gates.",
        "evidence_guidance": "CI test steps with 'continue-on-error: true' or '|| true' appended to test commands.",
        "recommendation": "Remove 'continue-on-error: true' and ensure test failures halt pipeline progression."
    },

    # 5. GitHub Actions / CI
    "CI-001": {
        "name": "Missing Continuous Integration (CI)",
        "category": "github actions / ci",
        "default_severity": "high",
        "description": "Repository lacks any continuous integration (CI) workflows.",
        "evidence_guidance": "Absence of .github/workflows directory or any valid CI workflow YAML files.",
        "recommendation": "Add a GitHub Actions workflow (.github/workflows/ci.yml) to validate builds and tests automatically."
    },
    "CI-002": {
        "name": "Dangerous Workflow Trigger (pull_request_target)",
        "category": "github actions / ci",
        "default_severity": "critical",
        "description": "Workflow uses pull_request_target trigger combined with checking out untrusted PR head code.",
        "evidence_guidance": "Workflow triggered on pull_request_target with checkout of PR ref or executing PR scripts.",
        "recommendation": "Use pull_request trigger instead of pull_request_target when executing code from forks."
    },
    "CI-003": {
        "name": "Excessive Workflow Permissions",
        "category": "github actions / ci",
        "default_severity": "high",
        "description": "GitHub Actions workflow grants overly permissive global permissions (e.g. write-all).",
        "evidence_guidance": "Top-level or job-level 'permissions: write-all' configured in workflow YAML.",
        "recommendation": "Adopt the principle of least privilege: declare explicit read-only permissions by default."
    },
    "CI-004": {
        "name": "Unpinned Third-Party GitHub Actions",
        "category": "github actions / ci",
        "default_severity": "medium",
        "description": "Third-party GitHub Actions referenced by mutable tags or branch names instead of full commit SHAs.",
        "evidence_guidance": "Actions from external organizations pinned to @main, @master, or @v1 instead of full 40-char SHA.",
        "recommendation": "Pin third-party GitHub Actions to specific commit SHAs with inline version comments."
    },
    "CI-005": {
        "name": "Skipped or Ineffective Validation Gates",
        "category": "github actions / ci",
        "default_severity": "medium",
        "description": "Workflow jobs or critical steps use skip conditions or continue-on-error that neutralize verification.",
        "evidence_guidance": "Steps with continue-on-error: true on linting or security checks.",
        "recommendation": "Enforce strict success criteria on validation steps before allowing merges or releases."
    },

    # 6. Security
    "SEC-001": {
        "name": "Exposed Hardcoded Credentials / Secrets",
        "category": "security",
        "default_severity": "critical",
        "description": "Hardcoded API keys, private tokens, passwords, or secret credentials found in committed code.",
        "evidence_guidance": "Direct assignment of API keys, AWS keys, database passwords, or JWT secrets in source code.",
        "recommendation": "Remove hardcoded credentials immediately, rotate exposed keys, and load secrets via environment variables."
    },
    "SEC-002": {
        "name": "Committed Sensitive Configuration / Environment Files",
        "category": "security",
        "default_severity": "critical",
        "description": "Sensitive environment files (e.g., .env, credentials.json, id_rsa) committed to version control.",
        "evidence_guidance": "Committed .env, .env.prod, service-account.json, or private key files in repository.",
        "recommendation": "Remove sensitive files from git tracking, add to .gitignore, and provide .env.example with dummy values."
    },
    "SEC-003": {
        "name": "Insecure Remote Script Execution",
        "category": "security",
        "default_severity": "high",
        "description": "Piping unverified remote URLs directly into shell interpreters (curl | bash) in CI or scripts.",
        "evidence_guidance": "Presence of 'curl -s ... | bash' or 'wget ... | sh' without checksum or signature verification.",
        "recommendation": "Download scripts, verify integrity via cryptographic checksums, and execute from a verified local copy."
    },

    # 7. Configuration
    "CONF-001": {
        "name": "Hardcoded Machine-Specific Paths",
        "category": "configuration",
        "default_severity": "medium",
        "description": "Source code or configuration contains local absolute user or operating-system specific file paths.",
        "evidence_guidance": "Paths such as /home/username/..., C:\\Users\\username\\..., or hardcoded root drive paths.",
        "recommendation": "Replace hardcoded absolute paths with relative paths or environment-variable based configuration."
    },
    "CONF-002": {
        "name": "Committed Local Environment Overrides",
        "category": "configuration",
        "default_severity": "medium",
        "description": "Local developer configurations or machine-specific connection strings committed into core repo.",
        "evidence_guidance": "Committed local_settings.py, config.local.json, or hardcoded localhost ports in production configs.",
        "recommendation": "Separate environment-specific configuration from code using twelve-factor config patterns."
    },

    # 8. Collaboration
    "COLLAB-001": {
        "name": "Unsafe Pull Request Automation",
        "category": "collaboration",
        "default_severity": "high",
        "description": "Automated merging or approving of pull requests without requiring human review or CI passage.",
        "evidence_guidance": "Workflows configured to auto-merge or auto-approve external PRs unconditionally.",
        "recommendation": "Require automated CI checks and code reviews prior to merging any pull request."
    },
    "COLLAB-002": {
        "name": "Lack of Review Guidance or Contribution Standards",
        "category": "collaboration",
        "default_severity": "low",
        "description": "Repository lacks PR templates, CONTRIBUTING guides, or issue templates to govern quality.",
        "evidence_guidance": "Absence of .github/pull_request_template.md, CONTRIBUTING.md, or issue templates in public repos.",
        "recommendation": "Add a CONTRIBUTING.md and pull request template to clarify code standards and review expectations."
    },

    # 9. Build and Release
    "BLD-001": {
        "name": "Missing Build Validation",
        "category": "build and release",
        "default_severity": "high",
        "description": "Deployable application or package lacks an automated build step to verify packaging integrity.",
        "evidence_guidance": "Repository builds containers or packages, but CI lacks steps to build docker image or package artifact.",
        "recommendation": "Incorporate a build verification job in CI to ensure compilations and packaging succeed."
    },
    "BLD-002": {
        "name": "Risky Release or Deployment Automation",
        "category": "build and release",
        "default_severity": "high",
        "description": "Deployment or release triggered automatically on untested branches or without environment protection.",
        "evidence_guidance": "Deployment triggers on non-main branches, or publish to PyPI/npm without tag or release gating.",
        "recommendation": "Gate release workflows to tagged releases or protected environments with approval gates."
    },
}

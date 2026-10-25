"""CLI Entry Point for DevOps Repository Auditing Agent."""

import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load local environment variables from .env if present
load_dotenv()

from agent.core import DevOpsAuditAgent
from agent.providers import get_llm_client
from agent.repo_manager import ClonedRepository


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Autonomous AI Agent for DevOps Repository Auditing with Evidence-Based Verification."
    )
    parser.add_argument(
        "--repo",
        type=str,
        required=True,
        help="Public GitHub repository URL (e.g. https://github.com/owner/repo) or local path.",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output path for the generated machine-readable JSON report (e.g. report.json).",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="LLM provider: 'gemini', 'openai', 'anthropic', 'groq', or 'mock' (default: auto-detect from env).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model identifier (e.g. 'gemini-2.5-flash', 'gpt-4o-mini', 'claude-3-5-sonnet-20241022').",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Optional API key override (otherwise loaded from environment).",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=15,
        help="Maximum agent reasoning and tool dispatch iterations (default: 15).",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in offline mock mode without making remote LLM API calls.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress terminal progress logs (output report only).",
    )
    return parser.parse_args()


def log_step(step_data: dict, quiet: bool = False):
    """Outputs live agent reasoning progress to console."""
    if quiet:
        return
    iteration = step_data.get("iteration")
    action = step_data.get("action")
    thought = step_data.get("thought", "")
    tool_name = step_data.get("tool_name")
    args = step_data.get("arguments", {})

    print(f"\n[Turn {iteration}] Action: {action}")
    if thought:
        print(f"  Reasoning: {thought}")
    if action == "call_tool":
        print(f"  Tool: {tool_name}({args})")


def print_summary_table(report, quiet: bool = False):
    """Prints a structured summary of the audit findings."""
    if quiet:
        return
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=f"DevOps Audit Summary: {report.repository}")
        table.add_column("Rule ID", style="cyan", no_wrap=True)
        table.add_column("Category", style="magenta")
        table.add_column("Severity", style="bold red")
        table.add_column("File:Line", style="yellow")
        table.add_column("Description")

        severity_colors = {
            "critical": "bold red",
            "high": "red",
            "medium": "yellow",
            "low": "blue",
        }

        for v in report.violations:
            loc = f"{v.file or 'N/A'}:{v.line or ''}".rstrip(":")
            sev_color = severity_colors.get(v.severity, "white")
            table.add_row(
                v.rule_id,
                v.category,
                f"[{sev_color}]{v.severity.upper()}[/{sev_color}]",
                loc,
                v.description,
            )

        console.print("\n")
        console.print(table)
        console.print(f"\nTotal Violations Detected: {len(report.violations)}\n")
    except ImportError:
        print(f"\n--- Audit Summary: {report.repository} ---")
        print(f"Total Violations Detected: {len(report.violations)}")
        for v in report.violations:
            loc = f"{v.file or 'N/A'}:{v.line or ''}".rstrip(":")
            print(f"[{v.severity.upper()}] {v.rule_id} ({v.category}) at {loc}: {v.description}")


def main():
    args = parse_arguments()

    provider = "mock" if args.mock else args.provider

    # Initialize LLM client
    try:
        llm_client = get_llm_client(
            provider=provider,
            model=args.model,
            api_key=args.api_key,
        )
    except Exception as e:
        sys.stderr.write(f"Configuration Error: {e}\n")
        sys.exit(1)

    # Initialize Auditor Agent
    callback = lambda step: log_step(step, quiet=args.quiet)
    agent = DevOpsAuditAgent(
        llm_client=llm_client,
        max_iterations=args.max_iterations,
        on_step_callback=callback,
    )

    if not args.quiet:
        print(f"Auditing Repository: {args.repo}")
        print(f"Cloning into isolated environment...")

    # Clone and inspect repository
    try:
        with ClonedRepository(args.repo) as repo_dir:
            if not args.quiet:
                print(f"Repository ready at sandbox: {repo_dir}")
                print("Starting autonomous inspection loop...")

            report = agent.audit(repo_url=args.repo, repo_dir=repo_dir)

    except TimeoutError as te:
        sys.stderr.write(f"Network / Timeout Error: {te}\n")
        sys.exit(1)
    except PermissionError as pe:
        sys.stderr.write(f"Security / Access Error: {pe}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Fatal Audit Error: {e}\n")
        sys.exit(1)

    # Write JSON report to output file
    try:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        json_content = report.model_dump_json_formatted()
        out_path.write_text(json_content, encoding="utf-8")
        if not args.quiet:
            print_summary_table(report, quiet=args.quiet)
            print(f"Audit completed successfully. Report saved to: {out_path}")
    except Exception as e:
        sys.stderr.write(f"Failed to write output report to '{args.output}': {e}\n")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()

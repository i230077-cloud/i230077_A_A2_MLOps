"""Core Agent loop implementing Observe -> Reason -> Select Tool -> Execute Tool -> Interpret -> Report."""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.prompts import INITIAL_INSPECTION_PROMPT, SYSTEM_PROMPT
from agent.providers import BaseLLMClient
from agent.sanitizer import clean_and_validate_violations
from agent.schema import AuditReport, Violation
from tools import TOOL_DEFINITIONS, RepoInspector


class DevOpsAuditAgent:
    """Autonomous AI Agent for DevOps Repository Auditing without external agent frameworks."""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        max_iterations: int = 15,
        on_step_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.llm_client = llm_client
        self.max_iterations = max_iterations
        self.on_step_callback = on_step_callback
        self.history: List[Dict[str, Any]] = []

    def _execute_tool(self, inspector: RepoInspector, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches tool call to RepoInspector safely."""
        tool_map = {
            "list_files": inspector.list_files,
            "read_file": inspector.read_file,
            "search_code": inspector.search_code,
            "git_log": inspector.git_log,
            "git_status": inspector.git_status,
            "inspect_ci_workflows": inspector.inspect_ci_workflows,
            "check_dependencies": inspector.check_dependencies,
        }

        func = tool_map.get(tool_name)
        if not func:
            return {"error": f"Unknown tool '{tool_name}'. Available tools: {list(tool_map.keys())}"}

        try:
            return func(**arguments)
        except TypeError as te:
            return {"error": f"Invalid arguments for tool '{tool_name}': {te}"}
        except Exception as e:
            return {"error": f"Tool execution failed: {e}"}

    def audit(self, repo_url: str, repo_dir: Path) -> AuditReport:
        """Executes the autonomous auditing loop over the given repository."""
        inspector = RepoInspector(repo_dir)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": INITIAL_INSPECTION_PROMPT.format(repo_url=repo_url)},
        ]

        final_raw_report: Optional[Dict[str, Any]] = None

        for iteration in range(1, self.max_iterations + 1):
            # Step 1: Model Reasoning and Tool Selection
            turn = self.llm_client.generate_turn(messages, TOOL_DEFINITIONS)
            thought = turn.get("thought", "")
            action = turn.get("action", "")

            # Notify step listener (for rich CLI updates)
            if self.on_step_callback:
                self.on_step_callback({
                    "iteration": iteration,
                    "thought": thought,
                    "action": action,
                    "tool_name": turn.get("tool_name"),
                    "arguments": turn.get("arguments"),
                })

            # Check if agent decided to finish
            if action == "finish" or "report" in turn:
                final_raw_report = turn.get("report")
                break

            # Handle Tool Execution
            if action == "call_tool":
                tool_name = turn.get("tool_name", "")
                arguments = turn.get("arguments", {})

                # Execute tool
                tool_result = self._execute_tool(inspector, tool_name, arguments)

                # Append assistant decision and observation to message history
                messages.append({
                    "role": "assistant",
                    "content": json.dumps({
                        "thought": thought,
                        "action": "call_tool",
                        "tool_name": tool_name,
                        "arguments": arguments,
                    }),
                })
                messages.append({
                    "role": "user",
                    "content": f"[OBSERVATION from {tool_name}]:\n{json.dumps(tool_result, indent=2)}\n"
                               f"Interpret these results and decide your next inspection step or output the final report.",
                })
            else:
                # If model produced ambiguous output, remind it of the protocol
                messages.append({
                    "role": "user",
                    "content": "Please continue by choosing either a tool to execute ('action': 'call_tool') "
                               "or emit the final audit report ('action': 'finish'). Respond in valid JSON.",
                })

        # If max iterations reached without explicit finish, prompt for final synthesis
        if not final_raw_report:
            messages.append({
                "role": "user",
                "content": "Inspection limit reached. Please synthesize all accumulated evidence and output the "
                           "final JSON audit report now using 'action': 'finish'.",
            })
            final_turn = self.llm_client.generate_turn(messages, TOOL_DEFINITIONS)
            final_raw_report = final_turn.get("report") or final_turn

        return self._process_final_report(repo_url, final_raw_report)

    def _process_final_report(self, repo_url: str, raw_report: Optional[Dict[str, Any]]) -> AuditReport:
        """Validates, sanitizes, and formats raw report into strict AuditReport contract."""
        if not raw_report or not isinstance(raw_report, dict):
            return AuditReport(repository=repo_url, violations=[])

        raw_violations = raw_report.get("violations", [])
        validated_violations: List[Violation] = []

        if isinstance(raw_violations, list):
            for v_data in raw_violations:
                if not isinstance(v_data, dict):
                    continue
                try:
                    # Provide defaults for missing fields if needed
                    v = Violation(
                        rule_id=str(v_data.get("rule_id", "GEN-001")),
                        category=str(v_data.get("category", "repository hygiene")),
                        severity=v_data.get("severity", "medium"),
                        file=v_data.get("file"),
                        line=v_data.get("line"),
                        description=str(v_data.get("description", "DevOps violation detected")),
                        evidence=str(v_data.get("evidence", "Observed during repository inspection")),
                        recommendation=str(v_data.get("recommendation", "Review and remediate issue")),
                    )
                    validated_violations.append(v)
                except Exception:
                    # Skip malformed violation items
                    continue

        # Sanitize secrets and deduplicate
        cleaned = clean_and_validate_violations(validated_violations)
        return AuditReport(
            repository=raw_report.get("repository") or repo_url,
            violations=cleaned,
        )

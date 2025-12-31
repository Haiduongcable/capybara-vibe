"""Work report generation for sub-agent execution."""

from capybara.core.execution.execution_log import ExecutionLog


def generate_work_report(
    response: str, execution_log: ExecutionLog | None, session_id: str, duration: float
) -> str:
    """Generate comprehensive work report from sub-agent execution.

    Returns detailed summary of:
    - What was accomplished
    - Files modified (created, edited, deleted)
    - Tools used and their outcomes
    - Any errors encountered
    - Success rate

    Format is optimized for parent agent to parse and act upon.
    """

    if not execution_log:
        # Fallback for agents without execution tracking
        return f"""Sub-agent Work Report (Session: {session_id})
Duration: {duration:.2f}s

{response}

Note: Detailed execution tracking not available."""

    # Build comprehensive report
    files_modified_list = ", ".join(sorted(execution_log.files_modified)) or "none"
    files_read_list = ", ".join(sorted(execution_log.files_read)) or "none"

    tool_summary_lines = [
        f"  - {tool}: {count}x" for tool, count in execution_log.tool_usage_summary.items()
    ]
    tool_summary = "\n".join(tool_summary_lines) if tool_summary_lines else "  (none)"

    error_section = ""
    if execution_log.errors:
        error_lines = [
            f"  - {tool}: {msg[:150]}{'...' if len(msg) > 150 else ''}"
            for tool, msg in execution_log.errors
        ]
        error_section = f"""
Errors Encountered ({len(execution_log.errors)}):
{chr(10).join(error_lines)}
"""

    # Extract first 300 chars of response as summary (avoid duplication in parent's output)
    response_summary = response[:300] + "..." if len(response) > 300 else response

    return f"""Sub-agent Work Report (Session: {session_id})
Duration: {duration:.2f}s | Success Rate: {execution_log.success_rate:.0%}

Quick Summary:
{response_summary}

Files Modified ({len(execution_log.files_modified)}): {files_modified_list}
Files Read ({len(execution_log.files_read)}): {files_read_list}

Tools Used ({len(execution_log.tool_executions)} total):
{tool_summary}
{error_section}
---
Parent: Use this concise report to inform your response. Don't repeat the full child response."""

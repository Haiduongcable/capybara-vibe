"""Diff formatting utilities for file edit operations."""

import os
from difflib import unified_diff


def generate_diff(
    original: str, modified: str, file_path: str, context_lines: int = 5
) -> str:
    """
    Generate diff-style output similar to Claude Code's Edit tool.

    Args:
        original: Original file content
        modified: Modified file content
        file_path: Path to the file being edited
        context_lines: Number of context lines to show around changes

    Returns:
        Formatted diff output with line numbers and change summary
    """
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)

    # Get unified diff
    diff = list(
        unified_diff(
            original_lines,
            modified_lines,
            fromfile=file_path,
            tofile=file_path,
            lineterm="",
            n=context_lines,
        )
    )

    if not diff:
        return "No changes detected"

    # Format the diff output
    filename = os.path.basename(file_path)
    output_lines = [f"Update({filename})"]

    # Count changes
    additions = sum(
        1 for line in diff if line.startswith("+") and not line.startswith("+++")
    )
    deletions = sum(
        1 for line in diff if line.startswith("-") and not line.startswith("---")
    )

    change_summary = []
    if additions > 0:
        change_summary.append(f"Added {additions} line{'s' if additions != 1 else ''}")
    if deletions > 0:
        change_summary.append(f"Removed {deletions} line{'s' if deletions != 1 else ''}")

    output_lines.append(f"  ⎿  {', '.join(change_summary)}")

    # Parse and format diff content
    current_line_num = 1
    for line in diff[2:]:  # Skip '---' and '+++' header lines
        if line.startswith("@@"):
            # Parse line numbers from @@ -old_start,old_count +new_start,new_count @@
            parts = line.split()
            if len(parts) >= 3:
                # parts[1] is "-old_start,old_count", parts[2] is "+new_start,new_count"
                # Extract starting line number from new file (parts[2])
                new_start = parts[2].lstrip("+").split(",")[0]
                try:
                    current_line_num = int(new_start)
                except ValueError:
                    current_line_num = 1
        elif line.startswith("-"):
            # Deleted line - show without line number since it's removed
            content = line[1:].rstrip("\n")
            output_lines.append(f"          -{content}")
        elif line.startswith("+"):
            # Added line with line number
            content = line[1:].rstrip("\n")
            output_lines.append(f"     {current_line_num:4d} +{content}")
            current_line_num += 1
        elif line.startswith(" "):
            # Context line
            content = line[1:].rstrip("\n")
            output_lines.append(f"     {current_line_num:4d}  {content}")
            current_line_num += 1

    return "\n".join(output_lines)

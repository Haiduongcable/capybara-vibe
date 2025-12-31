"""Diff formatting utilities for file edit operations."""

import os
from difflib import unified_diff

# Truncation settings
MAX_LINES_PER_TYPE = 2  # Max lines to show for additions OR deletions (total 4)
CONTEXT_LINES_DEFAULT = 1  # Minimal context for cleaner output
MAX_LINE_LENGTH = 60  # Truncate lines longer than this


def _truncate_line(content: str, max_length: int) -> str:
    """Truncate a line if it exceeds max_length."""
    if len(content) > max_length:
        return content[: max_length - 3] + "..."
    return content


def generate_diff(
    original: str,
    modified: str,
    file_path: str,
    context_lines: int = CONTEXT_LINES_DEFAULT,
    max_lines_per_type: int = MAX_LINES_PER_TYPE,
    max_line_length: int = MAX_LINE_LENGTH,
) -> str:
    """
    Generate truncated diff-style output for CLI display.

    Args:
        original: Original file content
        modified: Modified file content
        file_path: Path to the file being edited
        context_lines: Number of context lines to show around changes
        max_lines_per_type: Max lines to show per change type (+/-)
        max_line_length: Truncate lines longer than this

    Returns:
        Formatted diff output with truncation for long changes
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

    # Parse and format diff content with truncation
    current_line_num = 1
    shown_additions = 0
    shown_deletions = 0
    truncated_additions = 0
    truncated_deletions = 0

    for line in diff[2:]:  # Skip '---' and '+++' header lines
        if line.startswith("@@"):
            # Parse line numbers from @@ -old_start,old_count +new_start,new_count @@
            parts = line.split()
            if len(parts) >= 3:
                new_start = parts[2].lstrip("+").split(",")[0]
                try:
                    current_line_num = int(new_start)
                except ValueError:
                    current_line_num = 1
        elif line.startswith("-"):
            # Deleted line
            if shown_deletions < max_lines_per_type:
                content = _truncate_line(line[1:].rstrip("\n"), max_line_length)
                output_lines.append(f"          -{content}")
                shown_deletions += 1
            else:
                truncated_deletions += 1
        elif line.startswith("+"):
            # Added line
            if shown_additions < max_lines_per_type:
                content = _truncate_line(line[1:].rstrip("\n"), max_line_length)
                output_lines.append(f"     {current_line_num:4d} +{content}")
                shown_additions += 1
            else:
                truncated_additions += 1
            current_line_num += 1
        elif line.startswith(" "):
            # Context line - skip to save space
            current_line_num += 1

    # Add truncation indicators
    if truncated_deletions > 0:
        output_lines.append(f"          ... ({truncated_deletions} more deletions)")
    if truncated_additions > 0:
        output_lines.append(f"          ... ({truncated_additions} more additions)")

    return "\n".join(output_lines)

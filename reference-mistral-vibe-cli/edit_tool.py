#!/usr/bin/env python3
"""
Edit Tool - Python implementation
Performs exact string replacements in files with diff-style output
"""

import os
from typing import Tuple, List
from difflib import unified_diff


class EditTool:
    """Tool for making precise string replacements in files"""

    def __init__(self):
        self.context_lines = 5  # Number of context lines to show in diff

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False
    ) -> dict:
        """
        Perform exact string replacement in a file

        Args:
            file_path: Absolute path to the file to edit
            old_string: Exact text to find and replace
            new_string: Replacement text (must differ from old_string)
            replace_all: If True, replace all occurrences; if False, error on multiple matches

        Returns:
            dict with status, message, and diff output
        """
        # Validation
        if not os.path.isabs(file_path):
            return {
                "success": False,
                "error": "file_path must be an absolute path",
                "file_path": file_path
            }

        if not os.path.exists(file_path):
            return {
                "success": False,
                "error": f"File not found: {file_path}",
                "file_path": file_path
            }

        if old_string == new_string:
            return {
                "success": False,
                "error": "old_string and new_string must be different",
                "file_path": file_path
            }

        # Read the file
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to read file: {str(e)}",
                "file_path": file_path
            }

        # Check if old_string exists
        occurrences = original_content.count(old_string)

        if occurrences == 0:
            return {
                "success": False,
                "error": f"String not found in file: '{old_string}'",
                "file_path": file_path
            }

        # Check for multiple occurrences when replace_all is False
        if occurrences > 1 and not replace_all:
            return {
                "success": False,
                "error": f"String appears {occurrences} times in file. "
                        f"Use replace_all=True to replace all occurrences, "
                        f"or provide more context to make old_string unique.",
                "file_path": file_path,
                "occurrences": occurrences
            }

        # Perform replacement
        new_content = original_content.replace(old_string, new_string)

        # Write back to file
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to write file: {str(e)}",
                "file_path": file_path
            }

        # Generate diff output
        diff_output = self._generate_diff(
            original_content,
            new_content,
            file_path,
            occurrences,
            replace_all
        )

        return {
            "success": True,
            "file_path": file_path,
            "occurrences_replaced": occurrences,
            "replace_all": replace_all,
            "diff": diff_output,
            "message": self._generate_message(file_path, occurrences, replace_all)
        }

    def _generate_message(self, file_path: str, occurrences: int, replace_all: bool) -> str:
        """Generate success message"""
        filename = os.path.basename(file_path)

        if replace_all and occurrences > 1:
            return f"The file {file_path} has been updated. All {occurrences} occurrences were successfully replaced."
        else:
            return f"The file {file_path} has been updated."

    def _generate_diff(
        self,
        original: str,
        modified: str,
        file_path: str,
        occurrences: int,
        replace_all: bool
    ) -> str:
        """
        Generate diff-style output similar to Claude Code's Edit tool
        """
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        # Get unified diff
        diff = list(unified_diff(
            original_lines,
            modified_lines,
            fromfile=file_path,
            tofile=file_path,
            lineterm='',
            n=self.context_lines
        ))

        if not diff:
            return "No changes detected"

        # Format the diff output
        filename = os.path.basename(file_path)
        output_lines = []

        # Header
        output_lines.append(f"Update({filename})")

        # Count changes
        additions = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
        deletions = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))

        change_summary = []
        if additions > 0:
            change_summary.append(f"Added {additions} line{'s' if additions != 1 else ''}")
        if deletions > 0:
            change_summary.append(f"removed {deletions} line{'s' if deletions != 1 else ''}")

        output_lines.append(f"  ⎿  {', '.join(change_summary)}")

        # Parse and format diff content
        current_line_num = 0
        for line in diff[2:]:  # Skip the --- and +++ headers
            if line.startswith('@@'):
                # Parse line numbers from @@ -start,count +start,count @@
                parts = line.split()
                if len(parts) >= 2:
                    # Extract starting line number
                    new_start = parts[1].lstrip('+').split(',')[0]
                    try:
                        current_line_num = int(new_start)
                    except ValueError:
                        current_line_num = 1
            elif line.startswith('-'):
                # Deleted line
                content = line[1:].rstrip('\n')
                output_lines.append(f"     {current_line_num} -{content}")
            elif line.startswith('+'):
                # Added line
                content = line[1:].rstrip('\n')
                output_lines.append(f"     {current_line_num} +{content}")
                current_line_num += 1
            elif line.startswith(' '):
                # Context line
                content = line[1:].rstrip('\n')
                output_lines.append(f"     {current_line_num}  {content}")
                current_line_num += 1

        return '\n'.join(output_lines)

    def _generate_simple_diff(
        self,
        original: str,
        modified: str,
        file_path: str
    ) -> str:
        """
        Generate a simple line-by-line diff showing the changes with context
        """
        original_lines = original.split('\n')
        modified_lines = modified.split('\n')

        filename = os.path.basename(file_path)
        output = [f"Update({filename})"]

        # Find differing lines
        max_len = max(len(original_lines), len(modified_lines))
        changes_found = False

        for i in range(max_len):
            orig_line = original_lines[i] if i < len(original_lines) else None
            mod_line = modified_lines[i] if i < len(modified_lines) else None

            line_num = i + 1

            # Show context and changes
            if orig_line == mod_line:
                # Unchanged line
                if orig_line is not None:
                    output.append(f"     {line_num}  {orig_line}")
            else:
                changes_found = True
                # Changed/added/removed line
                if orig_line is not None:
                    output.append(f"     {line_num} -{orig_line}")
                if mod_line is not None:
                    output.append(f"     {line_num} +{mod_line}")

        if not changes_found:
            return f"Update({filename})\n  ⎿  No visible changes"

        # Add summary at position 1
        added = len(modified_lines) - len(original_lines)
        if added > 0:
            output.insert(1, f"  ⎿  Added {added} line(s)")
        elif added < 0:
            output.insert(1, f"  ⎿  Removed {abs(added)} line(s)")
        else:
            output.insert(1, f"  ⎿  Modified line(s)")

        return '\n'.join(output)


# Convenience function for easy usage
def edit_file(
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False
) -> dict:
    """
    Convenience function to edit a file

    Example:
        result = edit_file(
            file_path="/path/to/file.txt",
            old_string="Hello World",
            new_string="Hello Universe",
            replace_all=False
        )

        if result['success']:
            print(result['message'])
            print(result['diff'])
        else:
            print(f"Error: {result['error']}")
    """
    tool = EditTool()
    return tool.edit(file_path, old_string, new_string, replace_all)


if __name__ == "__main__":
    # Example usage and testing
    import sys

    print("=" * 70)
    print("Edit Tool - Python Implementation")
    print("=" * 70)
    print()

    # Create a test file
    test_file = "/tmp/edit_tool_test.txt"
    test_content = """Hello from Claude Code!
This is a test file.
Line 3 has some content.
Testing 123.
More content here."""

    with open(test_file, 'w') as f:
        f.write(test_content)

    print(f"Created test file: {test_file}")
    print(f"Original content:")
    print("-" * 70)
    with open(test_file, 'r') as f:
        for i, line in enumerate(f, 1):
            print(f"     {i}  {line.rstrip()}")
    print()

    # Test 1: Simple replacement
    print("TEST 1: Simple replacement")
    print("-" * 70)
    result = edit_file(
        file_path=test_file,
        old_string="Line 3 has some content.",
        new_string="Line 3 has been EDITED successfully!"
    )

    if result['success']:
        print(result['message'])
        print()
        print(result['diff'])
    else:
        print(f"Error: {result['error']}")
    print()

    # Test 2: Replace all occurrences
    print("TEST 2: Replace all occurrences")
    print("-" * 70)

    # Reset file
    with open(test_file, 'w') as f:
        f.write("World World World\nHello World\nGoodbye World")

    result = edit_file(
        file_path=test_file,
        old_string="World",
        new_string="Universe",
        replace_all=True
    )

    if result['success']:
        print(result['message'])
        print()
        print(result['diff'])
    else:
        print(f"Error: {result['error']}")
    print()

    # Test 3: Error case - multiple occurrences without replace_all
    print("TEST 3: Error case - multiple occurrences without replace_all")
    print("-" * 70)

    # Reset file
    with open(test_file, 'w') as f:
        f.write("Hello World\nHello World\nGoodbye")

    result = edit_file(
        file_path=test_file,
        old_string="Hello World",
        new_string="Hi Universe",
        replace_all=False
    )

    if result['success']:
        print(result['message'])
        print(result['diff'])
    else:
        print(f"Error: {result['error']}")
        print(f"Occurrences found: {result.get('occurrences', 'N/A')}")
    print()

    # Test 4: Error case - string not found
    print("TEST 4: Error case - string not found")
    print("-" * 70)

    result = edit_file(
        file_path=test_file,
        old_string="This does not exist",
        new_string="Something else",
        replace_all=False
    )

    if result['success']:
        print(result['message'])
        print(result['diff'])
    else:
        print(f"Error: {result['error']}")
    print()

    # Cleanup
    import os
    if os.path.exists(test_file):
        os.remove(test_file)
        print(f"Cleaned up test file: {test_file}")

    print()
    print("=" * 70)
    print("All tests completed!")
    print("=" * 70)

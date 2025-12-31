"""Rich-formatted diff rendering for terminal display."""

from rich.console import Console
from rich.text import Text


def render_diff(diff_output: str, file_path: str, console: Console) -> None:
    """
    Render diff output with Rich formatting to terminal.

    Displays immediately after edit_file execution with color-coded diff:
    - Green: additions (+)
    - Red: deletions (-)
    - Yellow: change summary (⎿)
    - Dim: context lines and line numbers
    - Bold: header (Update(filename))

    Args:
        diff_output: Formatted diff string from diff_formatter.generate_diff()
        file_path: Path to the modified file (unused, kept for compatibility)
        console: Rich Console instance for rendering

    Example:
        >>> diff_output = '''Update(test.txt)
        ...   ⎿  Added 1 line, Removed 1 line
        ...       1  This is a line
        ...       2 -Old content
        ...       2 +New content'''
        >>> render_diff(diff_output, "/path/to/test.txt", console)
        # Displays simple colored diff lines without box
    """
    for line in diff_output.split("\n"):
        # Skip empty lines
        if not line.strip():
            continue

        # Header: Update(filename)
        if line.startswith("Update("):
            console.print(Text(line, style="bold"))

        # Summary: ⎿ Added X, Removed Y
        elif "⎿" in line:
            console.print(Text(line, style="yellow"))

        # Added line: contains + after line number
        elif "+" in line and not line.startswith("Update("):
            stripped = line.lstrip()
            if stripped and (stripped[0].isdigit() or stripped.startswith("+")):
                console.print(Text(line, style="green"))
            else:
                console.print(Text(line, style="dim"))

        # Deleted line: contains - after line number
        elif "-" in line:
            stripped = line.lstrip()
            if stripped.startswith("-"):
                console.print(Text(line, style="red"))
            else:
                console.print(Text(line, style="dim"))

        # Context line or line number
        else:
            console.print(Text(line, style="dim"))

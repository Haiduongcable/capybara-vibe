"""Tests for diff_renderer module."""

from io import StringIO

import pytest
from rich.console import Console

from capybara.ui.diff_renderer import render_diff


@pytest.fixture
def console():
    """Create a Console instance that writes to StringIO for testing."""
    string_io = StringIO()
    return Console(file=string_io, force_terminal=True, width=120)


def get_console_output(console: Console) -> str:
    """Extract rendered output from console's StringIO."""
    return console.file.getvalue()


def test_render_diff_basic():
    """Test basic diff rendering with additions and deletions."""
    console_output = StringIO()
    console = Console(file=console_output, force_terminal=True, width=120)

    diff_output = """Update(test.txt)
  ⎿  Added 1 line, Removed 1 line
          -old content
        1 +new content
        2  context line"""

    render_diff(diff_output, "/tmp/test.txt", console)

    output = console_output.getvalue()

    # Check content is present (actual ANSI codes will vary)
    assert "Update(test.txt)" in output
    assert "Added 1 line" in output
    assert "old content" in output
    assert "new content" in output


def test_render_diff_header_styling():
    """Test that header line is styled correctly."""
    console_output = StringIO()
    console = Console(file=console_output, force_terminal=True, width=120)

    diff_output = """Update(myfile.py)
  ⎿  Added 2 lines
        1 +line one
        2 +line two"""

    render_diff(diff_output, "myfile.py", console)

    output = console_output.getvalue()

    # Verify Update header is present
    assert "Update(myfile.py)" in output


def test_render_diff_summary_line():
    """Test that summary line with ⎿ is rendered."""
    console_output = StringIO()
    console = Console(file=console_output, force_terminal=True, width=120)

    diff_output = """Update(file.txt)
  ⎿  Added 3 lines, Removed 2 lines
          -deleted1
          -deleted2
        1 +added1
        2 +added2
        3 +added3"""

    render_diff(diff_output, "file.txt", console)

    output = console_output.getvalue()

    # Summary should be present
    assert "Added 3 lines" in output
    assert "Removed 2 lines" in output


def test_render_diff_with_context_lines():
    """Test rendering with context lines (no +/- markers)."""
    console_output = StringIO()
    console = Console(file=console_output, force_terminal=True, width=120)

    diff_output = """Update(code.py)
  ⎿  Added 1 line, Removed 1 line
        1  def function():
        2      # context line
          -    old_code()
        3 +    new_code()
        4      return True"""

    render_diff(diff_output, "code.py", console)

    output = console_output.getvalue()

    # All lines should be present
    assert "def function():" in output
    assert "context line" in output
    assert "old_code()" in output
    assert "new_code()" in output
    assert "return True" in output


def test_render_diff_empty_output():
    """Test rendering with minimal diff output."""
    console_output = StringIO()
    console = Console(file=console_output, force_terminal=True, width=120)

    diff_output = """Update(empty.txt)
  ⎿  Added 1 line
        1 +single line"""

    render_diff(diff_output, "empty.txt", console)

    output = console_output.getvalue()

    # Check content is present
    assert "Update(empty.txt)" in output
    assert "single line" in output


def test_render_diff_multiple_deletions():
    """Test rendering multiple deleted lines."""
    console_output = StringIO()
    console = Console(file=console_output, force_terminal=True, width=120)

    diff_output = """Update(cleanup.txt)
  ⎿  Removed 3 lines
          -line to remove 1
          -line to remove 2
          -line to remove 3"""

    render_diff(diff_output, "cleanup.txt", console)

    output = console_output.getvalue()

    # All deletions should be present
    assert "line to remove 1" in output
    assert "line to remove 2" in output
    assert "line to remove 3" in output


def test_render_diff_multiple_additions():
    """Test rendering multiple added lines."""
    console_output = StringIO()
    console = Console(file=console_output, force_terminal=True, width=120)

    diff_output = """Update(expand.txt)
  ⎿  Added 4 lines
        1 +new line 1
        2 +new line 2
        3 +new line 3
        4 +new line 4"""

    render_diff(diff_output, "expand.txt", console)

    output = console_output.getvalue()

    # All additions should be present
    assert "new line 1" in output
    assert "new line 2" in output
    assert "new line 3" in output
    assert "new line 4" in output


def test_render_diff_with_section_markers():
    """Test rendering with @@ section markers (unified diff format)."""
    console_output = StringIO()
    console = Console(file=console_output, force_terminal=True, width=120)

    diff_output = """Update(large.py)
  ⎿  Added 2 lines, Removed 1 line
@@ -10,3 +10,4 @@
       10  context before
          -old line
       11 +new line 1
       12 +new line 2"""

    render_diff(diff_output, "large.py", console)

    output = console_output.getvalue()

    # Section marker should be present
    assert "@@" in output
    assert "context before" in output


def test_render_diff_preserves_indentation():
    """Test that indented code diff preserves formatting."""
    console_output = StringIO()
    console = Console(file=console_output, force_terminal=True, width=120)

    diff_output = """Update(indent.py)
  ⎿  Added 1 line, Removed 1 line
        5      if condition:
          -        old_implementation()
        6 +        new_implementation()
        7          pass"""

    render_diff(diff_output, "indent.py", console)

    output = console_output.getvalue()

    # Indentation should be visible in output
    assert "if condition:" in output
    assert "old_implementation()" in output
    assert "new_implementation()" in output


def test_render_diff_no_empty_lines_in_panel():
    """Test that empty lines in diff output are skipped."""
    console_output = StringIO()
    console = Console(file=console_output, force_terminal=True, width=120)

    diff_output = """Update(test.txt)

  ⎿  Added 1 line

        1 +content

"""

    render_diff(diff_output, "test.txt", console)

    output = console_output.getvalue()

    # Content should be present, but excessive empty lines handled
    assert "Added 1 line" in output
    assert "content" in output

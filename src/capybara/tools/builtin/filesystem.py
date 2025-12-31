"""Filesystem tools: read, write, edit."""

from pathlib import Path

import aiofiles

from capybara.tools.builtin.diff_formatter import generate_diff
from capybara.tools.registry import ToolRegistry


def register_filesystem_tools(registry: ToolRegistry) -> None:
    """Register filesystem tools with the registry."""

    @registry.tool(
        name="read_file",
        description="""Read contents of a file.

Usage:
- Returns file content with line numbers
- Supports offset/limit for large files
- Use for reading code, config, or any text file""",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
                "offset": {
                    "type": "integer",
                    "description": "Line number to start from (1-indexed)",
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max lines to read",
                    "default": 500,
                },
            },
            "required": ["path"],
        },
    )
    async def read_file(path: str, offset: int = 1, limit: int = 500) -> str:
        """Read file with line numbers."""
        try:
            async with aiofiles.open(path) as f:
                lines = await f.readlines()

            start = max(0, offset - 1)
            end = start + limit
            selected = lines[start:end]

            result = []
            for i, line in enumerate(selected, start=start + 1):
                result.append(f"{i:4d}|{line.rstrip()}")

            return "\n".join(result) if result else "(empty file)"
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except Exception as e:
            return f"Error: {e}"

    @registry.tool(
        name="write_file",
        description="""Write content to a file, creating if needed.

Usage:
- Creates parent directories automatically
- Overwrites existing content""",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute file path"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    )
    async def write_file(path: str, content: str) -> str:
        """Write content to file."""
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(path, "w") as f:
                await f.write(content)
            return f"Successfully wrote {len(content)} bytes to {path}"
        except Exception as e:
            return f"Error: {e}"

    @registry.tool(
        name="edit_file",
        description="""Edit file by replacing old_string with new_string.

Usage:
- old_string must be unique in the file (unless replace_all=true)
- Use replace_all=true to replace all occurrences
- Returns diff-style output showing changes""",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute file path"},
                "old_string": {"type": "string", "description": "Text to replace"},
                "new_string": {"type": "string", "description": "Replacement text"},
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences",
                    "default": False,
                },
            },
            "required": ["path", "old_string", "new_string"],
        },
    )
    async def edit_file(
        path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> str:
        """Edit file with string replacement and diff output."""
        try:
            # Validation
            if old_string == new_string:
                return "Error: old_string and new_string must be different"

            async with aiofiles.open(path) as f:
                original_content = await f.read()

            count = original_content.count(old_string)
            if count == 0:
                return f"Error: old_string not found in {path}"
            if count > 1 and not replace_all:
                return f"Error: old_string found {count} times. Use replace_all=true or make it unique."

            # Perform replacement
            new_content = original_content.replace(old_string, new_string)

            # Write back to file
            async with aiofiles.open(path, "w") as f:
                await f.write(new_content)

            # Generate diff output
            diff_output = generate_diff(original_content, new_content, path)

            # Generate success message
            if replace_all and count > 1:
                message = f"The file {path} has been updated. All {count} occurrences were successfully replaced."
            else:
                message = f"The file {path} has been updated."

            return f"{message}\n\n{diff_output}"

        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except Exception as e:
            return f"Error: {e}"

    @registry.tool(
        name="list_directory",
        description="""List contents of a directory.

Usage:
- Returns files and subdirectories
- Shows file sizes and types""",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to list"},
            },
            "required": ["path"],
        },
    )
    async def list_directory(path: str) -> str:
        """List directory contents."""
        try:
            p = Path(path)
            if not p.is_dir():
                return f"Error: Not a directory: {path}"

            entries = []
            for item in sorted(p.iterdir()):
                if item.is_dir():
                    entries.append(f"[DIR]  {item.name}/")
                else:
                    size = item.stat().st_size
                    entries.append(f"[FILE] {item.name} ({size:,} bytes)")

            return "\n".join(entries) if entries else "(empty directory)"
        except Exception as e:
            return f"Error: {e}"

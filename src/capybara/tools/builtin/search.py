"""Search tools: glob patterns and grep."""

import asyncio
import fnmatch
from pathlib import Path
from typing import Optional

from capybara.tools.registry import ToolRegistry


def register_search_tools(registry: ToolRegistry) -> None:
    """Register search tools with the registry."""

    @registry.tool(
        name="glob",
        description="""Find files matching a glob pattern.

Usage:
- Supports patterns like "**/*.py", "src/**/*.ts"
- Returns matching file paths
- Sorted by modification time (newest first)""",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern to match"},
                "path": {
                    "type": "string",
                    "description": "Base directory to search in",
                    "default": ".",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return",
                    "default": 100,
                },
            },
            "required": ["pattern"],
        },
    )
    async def glob_search(pattern: str, path: str = ".", limit: int = 100) -> str:
        """Find files matching glob pattern."""
        try:
            base = Path(path).resolve()
            if not base.exists():
                return f"Error: Path does not exist: {path}"

            matches = list(base.glob(pattern))

            # Sort by modification time (newest first)
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            matches = matches[:limit]

            if not matches:
                return f"No files matching '{pattern}' in {path}"

            return "\n".join(str(m.relative_to(base)) for m in matches)
        except Exception as e:
            return f"Error: {e}"

    @registry.tool(
        name="grep",
        description="""Search for a pattern in files.

Usage:
- Supports regex patterns
- Returns matching lines with file and line number
- Can filter by file glob pattern""",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {
                    "type": "string",
                    "description": "File or directory to search in",
                    "default": ".",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g., '*.py')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max matches to return",
                    "default": 50,
                },
            },
            "required": ["pattern"],
        },
    )
    async def grep_search(
        pattern: str,
        path: str = ".",
        file_pattern: Optional[str] = None,
        limit: int = 50,
    ) -> str:
        """Search for pattern in files using ripgrep or grep."""
        try:
            # Try ripgrep first, fall back to grep
            rg_available = await _check_command("rg")

            if rg_available:
                cmd = ["rg", "-n", "--no-heading", "-m", str(limit)]
                if file_pattern:
                    cmd.extend(["-g", file_pattern])
                cmd.extend([pattern, path])
            else:
                cmd = ["grep", "-rn", "-m", str(limit)]
                if file_pattern:
                    cmd.extend(["--include", file_pattern])
                cmd.extend([pattern, path])

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=30
            )

            if process.returncode == 0:
                output = stdout.decode("utf-8", errors="replace")
                lines = output.strip().split("\n")
                if len(lines) > limit:
                    lines = lines[:limit]
                    lines.append(f"... (truncated to {limit} matches)")
                return "\n".join(lines) if lines[0] else "No matches found"
            elif process.returncode == 1:
                return "No matches found"
            else:
                return f"Error: {stderr.decode('utf-8', errors='replace')}"

        except asyncio.TimeoutError:
            return "Error: Search timed out"
        except Exception as e:
            return f"Error: {e}"


async def _check_command(cmd: str) -> bool:
    """Check if a command is available."""
    try:
        process = await asyncio.create_subprocess_exec(
            "which",
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        return process.returncode == 0
    except Exception:
        return False

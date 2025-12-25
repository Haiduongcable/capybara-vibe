"""Bash execution tool with timeout and safety."""

import asyncio
import shlex
from typing import Optional


from capybara.tools.registry import ToolRegistry

# Commands that are potentially destructive
DANGEROUS_COMMANDS = frozenset([
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=/dev/zero",
    ":(){:|:&};:",  # Fork bomb
])


def register_bash_tools(registry: ToolRegistry) -> None:
    """Register bash tools with the registry."""

    @registry.tool(
        name="bash",
        description="""Execute a bash command.

Usage:
- Commands run with timeout protection
- Output is captured and returned
- Use for running tests, builds, git commands, etc.

Safety:
- Destructive commands are blocked
- Use responsibly in the working directory""",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The bash command to execute"},
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (max 300)",
                    "default": 60,
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for the command",
                },
            },
            "required": ["command"],
        },
    )
    async def bash(
        command: str, timeout: int = 60, cwd: Optional[str] = None
    ) -> str:
        """Execute bash command with timeout."""
        # Safety check
        for dangerous in DANGEROUS_COMMANDS:
            if dangerous in command:
                return f"Error: Blocked potentially dangerous command"

        # Clamp timeout
        timeout = min(max(timeout, 1), 300)

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return f"Error: Command timed out after {timeout}s"

            output_parts = []
            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))
            if stderr:
                output_parts.append(f"[stderr]\n{stderr.decode('utf-8', errors='replace')}")

            output = "\n".join(output_parts) if output_parts else "(no output)"

            # Truncate if too long
            if len(output) > 30000:
                output = output[:30000] + "\n... (truncated)"

            if process.returncode != 0:
                output += f"\n[exit code: {process.returncode}]"

            return output

        except Exception as e:
            return f"Error: {e}"

    @registry.tool(
        name="which",
        description="""Check if a command exists and get its path.""",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to check"},
            },
            "required": ["command"],
        },
    )
    async def which(command: str) -> str:
        """Check if command exists."""
        try:
            process = await asyncio.create_subprocess_exec(
                "which",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            if process.returncode == 0:
                return stdout.decode().strip()
            return f"Command not found: {command}"
        except Exception as e:
            return f"Error: {e}"

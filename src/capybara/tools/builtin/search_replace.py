"""Search and replace tool with safe block matching."""

import aiofiles
from typing import List, Tuple
from capybara.tools.registry import ToolRegistry

def parse_edits(content: str) -> List[Tuple[str, str]]:
    """Parse SEARCH/REPLACE blocks from content.
    
    Returns list of (search_block, replace_block) tuples.
    """
    edits = []
    lines = content.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        if line == '<<<<<<< SEARCH':
            i += 1
            search_lines = []
            while i < len(lines) and lines[i].strip() != '=======':
                search_lines.append(lines[i])
                i += 1
            
            if i >= len(lines):
                break
                
            # Skip =======
            i += 1
            
            replace_lines = []
            while i < len(lines) and lines[i].strip() != '>>>>>>> REPLACE':
                replace_lines.append(lines[i])
                i += 1
                
            if i < len(lines):
                # We found the end marker
                # Join with newlines to reconstruct the block
                # Note: We rely on the input preserving newlines
                edits.append(("\n".join(search_lines), "\n".join(replace_lines)))
                
        i += 1
        
    return edits

def format_error(path: str, search_block: str, file_content: str) -> str:
    """Format a detailed error message with context."""
    # TODO: Implement fuzzy matching or context finding to help the user
    return f"""Error: SEARCH block not found in {path}

Expected to find:
----------------
{search_block}
----------------

Suggestions:
- Check whitespace and indentation
- Verify the context matches exactly
- Use read_file to verify current content
"""

def register_search_replace_tools(registry: ToolRegistry) -> None:
    """Register search_replace tool with the registry."""

    @registry.tool(
        name="search_replace",
        description="""Apply consistent edits using SEARCH/REPLACE blocks.

Usage:
<<<<<<< SEARCH
[exact content to match]
=======
[new content to replace with]
>>>>>>> REPLACE

- SEARCH block must match exact file content (whitespace matters)
- Multiple blocks can be applied in one call
- Lines must be exact matches""",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute file path"},
                "content": {"type": "string", "description": "SEARCH/REPLACE blocks"},
            },
            "required": ["path", "content"],
        },
    )
    async def search_replace(path: str, content: str) -> str:
        """Apply SEARCH/REPLACE edits."""
        try:
            async with aiofiles.open(path, "r") as f:
                file_content = await f.read()

            edits = parse_edits(content)
            
            if not edits:
                return "Error: No valid SEARCH/REPLACE blocks found. Ensure you use <<<<<<< SEARCH, =======, and >>>>>>> REPLACE markers."

            new_content = file_content
            
            # Validate all edits before applying any
            # Note: This is tricky if edits overlap or are order-dependent.
            # For simplicity, we assume they are sequential and distinct, or applied to the result of previous.
            # But verifying existence in original content is safer if they don't overlap.
            # If we apply sequentially, the subsequent search blocks must match the content *after* previous edits.
            
            # Let's apply sequentially.
            applied_count = 0
            
            for search_block, replace_block in edits:
                # Normalizing newlines might be needed?
                # For now, strict match.
                
                if search_block not in new_content:
                     return format_error(path, search_block, new_content)
                
                count = new_content.count(search_block)
                if count > 1:
                    return f"Error: SEARCH block found {count} times in {path}. Please provide more context to make it unique."

                new_content = new_content.replace(search_block, replace_block, 1)
                applied_count += 1

            async with aiofiles.open(path, "w") as f:
                await f.write(new_content)

            return f"Successfully applied {applied_count} edit(s) to {path}"
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except Exception as e:
            return f"Error: {e}"

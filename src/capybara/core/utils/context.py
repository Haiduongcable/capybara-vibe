import os
import subprocess
import sys
import fnmatch
from pathlib import Path
from typing import List, Generator

from capybara.core.config.safety import is_dangerous_directory, DANGEROUS_DIRECTORY_WARNING

IGNORE_DIRS = {
    '.git', 'node_modules', '__pycache__', 'venv', '.env', 'dist', 'build', 
    'coverage', '.idea', '.vscode', 'target', 'out', '.next', '.nuxt', 
    '.pytest_cache', '*.egg-info', 'vendor', 'tmp', 'temp', 'logs'
}

IGNORE_EXTENSIONS = {
    '.pyc', '.o', '.obj', '.dll', '.so', '.exe', '.class', 
    '.min.js', '.min.css', '.bundle.js', '.chunk.js'
}

PROJECT_DOC_FILES = [
    "README.md", "README", "architecture.md", "ARCHITECTURE.md", 
    "CONTRIBUTING.md", "pyproject.toml", "package.json", "go.mod"
]

def get_os_info() -> str:
    """Get operating system and shell information."""
    platform_map = {
        "win32": "Windows",
        "darwin": "macOS",
        "linux": "Linux",
    }
    os_name = platform_map.get(sys.platform, "Unix-like")
    
    # Determine default shell
    if sys.platform == "win32":
        shell = os.environ.get("COMSPEC", "cmd.exe")
    else:
        shell = os.environ.get("SHELL", "/bin/sh")
        
    return f"OS: {os_name}\nShell: {shell}"

def _load_project_docs(root: Path, max_chars: int = 2000) -> str:
    """Load key project documentation files."""
    docs = []
    total_len = 0
    
    for filename in PROJECT_DOC_FILES:
        path = root / filename
        if path.exists() and path.is_file():
            try:
                content = path.read_text(errors='ignore')
                if len(content) > max_chars:
                     content = content[:max_chars] + "\n... (truncated)"
                
                docs.append(f"--- {filename} ---\n{content}\n")
                total_len += len(content)
                if total_len > max_chars * 2: # Global limit 
                    break
            except Exception:
                continue
                
    return "\n".join(docs)

async def build_project_context(path: str = ".") -> str:
    """Build project snapshot for system prompt."""
    root = Path(path).resolve()
    
    if is_dangerous_directory(root):
        return DANGEROUS_DIRECTORY_WARNING
        
    os_info = get_os_info()
    structure = _get_directory_structure(root)
    git_status = _get_git_status(root)
    project_docs = _load_project_docs(root)
    
    return f"""Project Context:
{os_info}

Directory Structure:
{structure}

Git Status:
{git_status}

Key Documentation:
{project_docs}
"""

def _get_directory_structure(root: Path, max_depth: int = 3) -> str:
    """Get a tree-like string of the directory structure."""
    lines = []
    
    # Check if git ls-files works (respects gitignore)
    # But git ls-files only lists tracked files. New files prompt "git status".
    # Mixing os.walk with ignore list is safer for now.
    
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            # Modify dirnames in-place to skip ignored
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith('.')]
            dirnames.sort()
            
            path_obj = Path(dirpath)
            # Calculate depth relative to root
            try:
                rel_path = path_obj.relative_to(root)
                depth = len(rel_path.parts)
                if rel_path == Path('.'):
                    depth = 0
            except ValueError:
                depth = 0
                
            if depth > max_depth:
                dirnames.clear()
                continue
                
            indent = "  " * depth
            if depth == 0:
                # lines.append(f"{root.name}/") # Root is assumed context
                pass
            else:
                lines.append(f"{indent}{path_obj.name}/")
            
            sub_indent = "  " * (depth + 1)
            filenames.sort()
            count = 0
            for f in filenames:
                if f.startswith('.'): continue
                if any(f.endswith(ext) for ext in IGNORE_EXTENSIONS): continue
                
                lines.append(f"{sub_indent}{f}")
                count += 1
                if count > 20:
                    lines.append(f"{sub_indent}... ({len(filenames) - 20} more files)")
                    break
                    
        return "\n".join(lines) if lines else "(empty)"
    except Exception as e:
        return f"Error scanning directory: {e}"

def _get_git_status(root: Path) -> str:
    """Get concise git status."""
    try:
        # Check if git installed
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        
        # git status --short
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode != 0:
            return "(git error or not a repo)"
            
        output = result.stdout.strip()
        if not output:
             # Try git log
             log_result = subprocess.run(
                ["git", "log", "-1", "--oneline"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=2
            )
             if log_result.returncode == 0:
                 return f"(clean) Last commit: {log_result.stdout.strip()}"
             return "(clean)"
             
        # Limit lines
        lines = output.splitlines()
        if len(lines) > 10:
             return "\n".join(lines[:10]) + f"\n... ({len(lines)-10} more changes)"
        return output
    except Exception:
        return "(unavailable)"

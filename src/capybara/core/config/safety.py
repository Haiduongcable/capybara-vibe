from pathlib import Path

DANGEROUS_PATHS = [
    Path("/"),  # Root
    Path("/usr"),
    Path("/etc"),
    Path("/var"),
    Path("/bin"),
    Path("/sbin"),
]


def is_dangerous_directory(path: Path) -> bool:
    """Check if directory is unsafe for project scanning."""
    try:
        resolved = path.resolve()

        # Check explicit equality for Home (working in subdirs is fine)
        if resolved == Path.home().resolve():
            return True

        # Check system paths and their children
        for dangerous in DANGEROUS_PATHS:
            try:
                dangerous_resolved = dangerous.resolve()

                # If path IS the dangerous directory exactly
                if resolved == dangerous_resolved:
                    return True

                # Special case: Skip root (/) for relative-to check
                # because EVERYTHING is relative to root
                if dangerous_resolved == Path("/").resolve():
                    continue

                # If path is inside dangerous directory
                if resolved.is_relative_to(dangerous_resolved):
                    return True
            except ValueError:
                # is_relative_to raises ValueError if not relative
                continue

        return False
    except Exception:
        # On error (e.g. permission denied resolving), assume unsafe
        return True


DANGEROUS_DIRECTORY_WARNING = """
⚠️ WARNING: You are working in a potentially sensitive or system directory.
The agent will NOT scan the directory structure automatically to protect your system.
Please specify exact file paths when requesting file operations.
"""

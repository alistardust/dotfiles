"""Path validation and safety utilities."""
import os
import sys
from pathlib import Path


def validate_no_symlink(path: Path) -> None:
    """Abort if path or any ancestor is a symlink.

    Walks each component of the path checking for symlinks.
    This catches both symlinked files and symlinked parent directories.
    """
    # Check the file itself
    if path.exists() and path.is_symlink():
        print(f"Error: refusing symlinked file: {path}", file=sys.stderr)
        sys.exit(1)

    # Walk parent chain checking for symlinks
    parent = path.parent
    while parent != parent.parent:
        if parent.exists() and parent.is_symlink():
            print(f"Error: symlink detected in parent path: {parent}", file=sys.stderr)
            sys.exit(1)
        parent = parent.parent


def validate_output_path(output_path: Path) -> Path:
    """Resolve and validate output path is within home or cwd."""
    resolved = output_path.resolve()
    home = Path.home().resolve()
    cwd = Path.cwd().resolve()

    if not (str(resolved).startswith(str(home)) or str(resolved).startswith(str(cwd))):
        print(
            f"Error: output path must be within home directory or working directory: {output_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    return resolved


def secure_write(path: Path, content: str) -> None:
    """Write content to path with 0600 permissions atomically."""
    validate_no_symlink(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(str(path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        f = os.fdopen(fd, "w")
    except Exception:
        os.close(fd)
        raise
    with f:
        f.write(content)

import os
from pathlib import Path
from typing import List, Dict, Optional


class WorkspaceManager:
    """Scans and manages codebase contexts to take advantage of 0x Alpha's 1.05M context window."""

    IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    IGNORE_EXTS = {".exe", ".dll", ".so", ".png", ".jpg", ".jpeg", ".pyc", ".zip", ".tar", ".gz"}

    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = Path(root_dir) if root_dir else None

    def set_root(self, path: str):
        self.root_dir = Path(path)

    def scan_files(self, max_file_size_kb: int = 500) -> List[Path]:
        """Recursively fetches printable project files, skipping binary and ignored directories."""
        if not self.root_dir or not self.root_dir.is_dir():
            return []

        valid_files = []
        for root, dirs, files in os.walk(self.root_dir):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]

            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() in self.IGNORE_EXTS:
                    continue

                # Skip files exceeding maximum size limit
                if file_path.stat().st_size > max_file_size_kb * 1024:
                    continue

                valid_files.append(file_path)

        return valid_files

    def build_context_prompt(self) -> str:
        """Formats the whole repository into a structured Markdown prompt for long-context analysis."""
        files = self.scan_files()
        if not files:
            return ""

        context_blocks = ["# Project Codebase Context\n"]
        for file_path in files:
            try:
                rel_path = file_path.relative_to(self.root_dir)
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                context_blocks.append(f"## File: `{rel_path}`\n```\n{content}\n```\n")
            except Exception as e:
                context_blocks.append(f"<!-- Failed to read file {file_path}: {e} -->\n")

        return "\n".join(context_blocks)

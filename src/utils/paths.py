"""Project path resolution — paths work regardless of process working directory."""

from __future__ import annotations

import os
from pathlib import Path

# ai-news-agent/ (parent of src/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_path(*parts: str) -> Path:
    """Build an absolute path under the project root."""
    return PROJECT_ROOT.joinpath(*parts)


def resolve_path(path: str | Path) -> Path:
    """Resolve relative paths against PROJECT_ROOT; leave absolute paths unchanged."""
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return PROJECT_ROOT / resolved


def resolve_env_path(env_var: str, default: str) -> Path:
    """Resolve a path from an environment variable with a project-relative default."""
    return resolve_path(os.getenv(env_var, default))

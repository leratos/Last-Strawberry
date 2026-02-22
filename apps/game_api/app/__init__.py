"""Greenfield Game API package marker.

Local dev convenience:
- make shared local packages importable for `uvicorn --reload` without
  requiring a manually exported `PYTHONPATH`.

This should be replaced by proper packaging/install steps once the Greenfield
services are split into independently installable distributions.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_local_package_paths() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    candidate_paths = (
        repo_root,
        repo_root / "packages" / "shared_schemas",
        repo_root / "packages" / "rules_engine",
    )
    for path in candidate_paths:
        if not path.exists():
            continue
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


_bootstrap_local_package_paths()

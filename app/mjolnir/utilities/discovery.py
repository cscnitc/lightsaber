# Licensed under the Apache-2.0 license
# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path

from utilities.logger import logger


def discover_source_files(code_dir: str, job) -> list:
    """Finds all source files under the target directory matching the requested extensions, optionally limiting count."""

    extensions = set(job.get("extensions") or ["rs", "c", "h"])
    src_dirs = job.get("srcDirs") or ["."]
    max_files = job.get("maxFiles")

    code_path = Path(code_dir).resolve()
    files_to_scan = []

    # Explicit file list (used for curated shortlists): relative repo paths,
    # verified against the checkout; missing entries are logged and skipped.
    explicit = job.get("files")
    if explicit:
        for rel in explicit:
            cand = (code_path / rel).resolve()
            try:
                rel_norm = str(cand.relative_to(code_path))
            except ValueError:
                rel_norm = rel
            if cand.is_file():
                files_to_scan.append(rel_norm)
            else:
                from utilities.logger import logger as _lg
                _lg.warning(f"[discovery] shortlist entry missing, skipping: {rel}")
        return files_to_scan

    for s_dir in src_dirs:
        scan_path = (code_path / s_dir).resolve()
        if not scan_path.exists():
            continue
        for root, _, files in os.walk(scan_path):
            root_path = Path(root)
            # Skip hidden directories starting with '.' (like .git, .bazel, etc)
            if any(part.startswith(".") for part in root_path.parts):
                continue
            for file in files:
                file_path = root_path / file
                ext = file_path.suffix.lstrip(".").lower()
                if ext in extensions:
                    try:
                        rel_path = str(file_path.relative_to(code_path))
                    except ValueError:
                        rel_path = str(file_path)
                    files_to_scan.append(rel_path)

    if max_files and isinstance(max_files, int) and len(files_to_scan) > max_files:
        logger.info(
            f"     [Config Loader] Limiting scan from {len(files_to_scan)} to first {max_files} files (maxFiles set)"
        )
        files_to_scan = files_to_scan[:max_files]

    return files_to_scan

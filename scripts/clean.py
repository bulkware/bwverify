"""Remove known project build artifacts without using broad Git ignore rules."""

import argparse
import os
from pathlib import Path
import shutil


# Only these root outputs and caches are disposable; local settings are preserved.
ROOT_OUTPUTS = (
    "build", "dist", ".eggs", "htmlcov", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".pytype", ".hypothesis", ".coverage", "coverage.xml",
)


def cleanup_paths(root):
    """Find known outputs, scanning only source/test/script trees for bytecode."""
    # Seed the result with fixed root artifacts, then add safely discovered cache files.
    candidates = {root / name for name in ROOT_OUTPUTS}
    for pattern in ("*.egg-info", ".coverage.*"):
        candidates.update(root.glob(pattern))
    # A source-tree egg-info directory is created by some editable-install workflows.
    if not (root / "src").is_symlink():
        candidates.update((root / "src").glob("*.egg-info"))
    candidates.add(root / "__pycache__")
    # Never follow links while looking for bytecode: a cleanup must stay in this checkout.
    for name in ("src", "tests", "scripts"):
        tree = root / name
        if tree.is_symlink():
            continue
        for directory, subdirectories, files in os.walk(tree, followlinks=False):
            base = Path(directory)
            subdirectories[:] = [name for name in subdirectories if base / name not in candidates]
            if "__pycache__" in subdirectories:
                candidates.add(base / "__pycache__")
                subdirectories.remove("__pycache__")
            for filename in files:
                if filename.endswith((".pyc", ".pyo")):
                    candidates.add(base / filename)
    return sorted(path for path in candidates if path.exists() or path.is_symlink())


def main():
    """Preview or remove generated paths relative to this script's checkout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Only list paths to remove")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    # Print every target first in dry-run mode, using the same selection as real cleanup.
    for path in cleanup_paths(root):
        print(f"{'Would remove' if arguments.dry_run else 'Removing'} {path.relative_to(root)}")
        if arguments.dry_run:
            continue
        # Unlink symlinks themselves, never recurse into their targets.
        if path.is_symlink() or not path.is_dir():
            path.unlink()
        else:
            shutil.rmtree(path)


if __name__ == "__main__":
    main()

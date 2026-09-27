"""Verify cleanup removes artifacts while preserving developer files."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


# Run the cleanup tool in a disposable tree to prove it never selects user files.
class CleanTests(unittest.TestCase):
    """Run cleanup in a disposable checkout, never against real build outputs."""

    def test_cleanup_preview_preservation_and_repeat_run(self):
        """Preview is read-only and cleanup preserves settings and symlink targets."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "checkout"
            (root / "scripts").mkdir(parents=True)
            script = root / "scripts/clean.py"
            shutil.copy2(Path(__file__).resolve().parents[1] / "scripts/clean.py", script)
            generated = (
                "build/rpm/source.tar.gz", "dist/app.whl", "src/app.egg-info/PKG-INFO",
                "src/app/__pycache__/app.pyc", "tests/old.pyc", ".coverage",
                ".pytest_cache/state",
            )
            preserved = (
                ".env", "config.cfg", "AGENTS.md", "LOCAL_NOTES.md", ".git/config",
                ".venv/lib/keep.pyc", "src/app/main.py", "data/icon.svg",
            )
            for name in (*generated, *preserved):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture", encoding="utf-8")

            # A cache symlink must not cause deletion outside the checkout.
            outside = Path(directory) / "external"
            outside.mkdir()
            (outside / "keep.pyc").write_text("keep", encoding="utf-8")
            (root / "__pycache__").symlink_to(outside, target_is_directory=True)
            command = [sys.executable, str(script)]
            result = subprocess.run([*command, "--dry-run"], check=True,
                                    capture_output=True, text=True)
            self.assertIn("Would remove build", result.stdout)
            for name in (*generated, *preserved):
                self.assertTrue((root / name).exists(), name)

            # A second invocation should be harmless after the first cleanup.
            for _ in range(2):
                subprocess.run(command, check=True, capture_output=True)
            for name in generated:
                self.assertFalse((root / name).exists(), name)
            for name in preserved:
                self.assertEqual((root / name).read_text(encoding="utf-8"), "fixture", name)
            self.assertFalse((root / "__pycache__").is_symlink())
            self.assertTrue((outside / "keep.pyc").exists())

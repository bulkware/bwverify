"""Test release metadata synchronization without changing repository files."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class PrepareReleaseTests(unittest.TestCase):
    """Exercise the release helper against isolated project fixtures."""

    def test_updates_release_metadata_from_the_latest_changelog_release(self):
        """Synchronize a temporary project's version and AppStream release entry."""
        repository_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            for name in ("prepare_release.py", "package_metadata.py"):
                shutil.copy2(repository_root / "scripts" / name, scripts / name)
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n## [Unreleased]\n\n## [1.2.3] - 2026-09-20\n\n"
                "### Added\n\n- Prepared a release.\n",
                encoding="utf-8",
            )
            (root / "pyproject.toml").write_text(
                "[project]\nname = \"bwVerify\"\nversion = \"0.0.0\"\n",
                encoding="utf-8",
            )
            data = root / "data"
            data.mkdir()
            appstream = data / "org.bulkware.bwverify.metainfo.xml"
            appstream.write_text(
                "<component>\n  <releases>\n  </releases>\n</component>\n", encoding="utf-8"
            )

            subprocess.run([sys.executable, str(scripts / "prepare_release.py")], check=True)

            self.assertIn('version = "1.2.3"', (root / "pyproject.toml").read_text())
            self.assertIn(
                '<release version="1.2.3" date="2026-09-20"/>', appstream.read_text()
            )

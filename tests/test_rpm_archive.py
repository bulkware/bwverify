"""Check local RPM source packaging without requiring RPM build dependencies."""

import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest


# Archive checks need only the tools used for staging; they intentionally avoid rpmbuild.
@unittest.skipUnless(shutil.which("bash") and shutil.which("tar"), "Requires Bash and tar")
class RpmArchiveTests(unittest.TestCase):
    """Exercise the real wrapper against a source directory without a repository."""

    def test_archive_uses_local_package_inputs(self):
        """Package current sources while excluding unrelated files and caches."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = Path(__file__).resolve().parents[1] / "scripts"
            script = scripts / "build-rpm.sh"
            generator = scripts / "generate_package_changelogs.py"
            # The staged archive must contain this exact allowlist and nothing from the fixture.
            inputs = {
                "pyproject.toml": (
                    "[project]\n"
                    'name = "bwverify"\n'
                    'version = "1.0.0"\n'
                    'authors = [{name = "Example Maintainer", email = "example@example.com"}]\n'
                ),
                "README.md": "Local readme\n",
                "CHANGELOG.md": (
                    "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2026-09-19\n\n"
                    "### Added\n\n- Local release.\n"
                ),
                "ICONS.md": "# Icons\n",
                "LICENSE.md": "License\n",
                "Makefile": "all:\n\t@true\n",
                "src/bwverify/__init__.py": "# Local application\n",
                "src/bwverify/icons/open.svg": "<svg/>\n",
                "src/bwverify/icons/oxygen/open.svg": "<svg/>\n",
                "src/bwverify/icons/tango/open.svg": "<svg/>\n",
                "data/org.bulkware.bwverify.desktop": "[Desktop Entry]\n",
                "data/org.bulkware.bwverify.metainfo.xml": "<component/>\n",
                "data/org.bulkware.bwverify.xml": "<mime-info/>\n",
                "data/icons/hicolor/scalable/apps/org.bulkware.bwverify.svg": "<svg/>\n",
                "data/icons/hicolor/symbolic/apps/org.bulkware.bwverify-symbolic.svg":
                    "<svg/>\n",
                "tests/test_placeholder.py": "# Local test\n",
                "scripts/clean.py": "# Local cleanup helper\n",
                "examples/example.sfv": "local example\n",
                "packaging/rpm/bwverify.spec": (
                    "Name: bwverify\nVersion: 0.0.0\nRelease: 1%{?dist}\n%changelog\n"
                ),
                "debian/changelog": "bwverify (1.0.0-1) unstable; urgency=medium\n",
            }
            # Create package inputs and unrelated local files without Git metadata.
            for name, contents in {
                **inputs,
                ".env": "private data\n",
                "AGENTS.md": "local instructions\n",
                "src/bwverify/__pycache__/cached.pyc": "cache\n",
                "build/old-artifact": "old output\n",
            }.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents)
            (root / "scripts").mkdir(exist_ok=True)
            shutil.copy2(script, root / "scripts/build-rpm.sh")
            shutil.copy2(generator, root / "scripts/generate_package_changelogs.py")
            inputs["scripts/build-rpm.sh"] = script.read_text()
            inputs["scripts/generate_package_changelogs.py"] = generator.read_text()

            # Capture the selected spec and make any accidental Git invocation fail.
            binaries = root / "bin"
            binaries.mkdir()
            for name, contents in {
                "rpmbuild": '#!/bin/bash\ncat "${@: -1}" > "$RPM_TEST_SPEC"\n',
                "git": "#!/bin/bash\nexit 99\n",
            }.items():
                executable = binaries / name
                executable.write_text(contents)
                executable.chmod(0o755)
            captured_spec = root / "captured.spec"
            environment = dict(os.environ, PATH=f"{binaries}{os.pathsep}{os.environ['PATH']}",
                               RPM_TEST_SPEC=str(captured_spec))
            subprocess.run(["bash", str(root / "scripts/build-rpm.sh")], check=True,
                           env=environment, cwd=binaries, capture_output=True)

            # Check every archived file and its contents, including current local edits.
            archive = root / "build/rpm/rpmbuild/SOURCES/bwverify-1.0.0.tar.gz"
            with tarfile.open(archive) as source:
                files = {item.name for item in source.getmembers() if item.isfile()}
                self.assertEqual(files, {f"bwverify-1.0.0/{name}" for name in inputs})
                for name, contents in inputs.items():
                    self.assertEqual(source.extractfile(f"bwverify-1.0.0/{name}").read(),
                                     contents.encode())
            captured = captured_spec.read_text()
            self.assertIn("Version:        1.0.0", captured)
            self.assertIn("- Added: Local release.", captured)

    def test_missing_version_fails_before_build(self):
        """Reject incomplete metadata without creating build output."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "pyproject.toml").write_text('[project]\nname = "bwVerify"\n')
            script = Path(__file__).resolve().parents[1] / "scripts/build-rpm.sh"
            shutil.copy2(script, root / "scripts/build-rpm.sh")
            result = subprocess.run(["bash", str(root / "scripts/build-rpm.sh")],
                                    check=False, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unable to determine the package version", result.stderr)
            self.assertFalse((root / "build").exists())

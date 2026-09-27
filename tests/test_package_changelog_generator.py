"""Test native package changelog generation from the project release notes."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest


# The generator is invoked as a script to cover its real command-line integration.
class PackageChangelogGeneratorTests(unittest.TestCase):
    """Exercise the generator in disposable project roots."""

    def test_repository_metadata_is_valid_toml(self):
        """Keep the metadata consumed by native package builders TOML-valid."""
        repository_root = Path(__file__).resolve().parents[1]
        metadata_path = repository_root / "pyproject.toml"

        project = tomllib.loads(metadata_path.read_text(encoding="utf-8"))["project"]

        self.assertEqual(project["version"], "1.0.0")
        self.assertEqual(project["authors"][0]["email"], "antice@kapsi.fi")
        self.assertEqual(project["license"], "GPL-3.0-or-later")
        self.assertEqual(project["license-files"], ["LICENSE.md"])
        self.assertFalse(any(item.startswith("License ::") for item in project["classifiers"]))

        # The distributable license file must contain the complete GPLv3 text.
        license_text = (repository_root / "LICENSE.md").read_text(encoding="utf-8")
        self.assertTrue(license_text.startswith("                    GNU GENERAL PUBLIC LICENSE"))
        self.assertIn("                     END OF TERMS AND CONDITIONS", license_text)

    @staticmethod
    def create_project(root: Path, changelog: str) -> Path:
        """Create the smallest valid release project and return its generator path."""
        # Each case owns its metadata and release notes, preventing mutations in this repo.
        scripts = root / "scripts"
        scripts.mkdir()
        generator = Path(__file__).resolve().parents[1] / "scripts/generate_package_changelogs.py"
        shutil.copy2(generator, scripts / generator.name)
        (root / "pyproject.toml").write_text(
            "[project]\n"
            "name = \"bwVerify\"\n"
            "version = \"1.2.3\"\n"
            "authors = [{name = \"Example Maintainer\", email = \"example@example.com\"}]\n",
            encoding="utf-8",
        )
        (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
        return scripts / generator.name

    def test_generates_idempotent_rpm_and_debian_entries(self):
        """Generate both native formats once and preserve them on a repeat run."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generator = self.create_project(
                root,
                "# Changelog\n\n## [Unreleased]\n\n## [1.2.3] - 2026-09-20\n\n"
                "### Added\n\n- Added native changelog generation.\n\n### Fixed\n\n"
                "- Rejected malformed release notes before a package build.\n",
            )
            spec = root / "bwverify.spec"
            debian_changelog = root / "debian.changelog"
            spec.write_text("Name: bwverify\nVersion: 0.0.0\nRelease: 1%{?dist}\n%changelog\n",
                            encoding="utf-8")
            debian_changelog.write_text("older entry\n", encoding="utf-8")
            command = [
                sys.executable, str(generator), "--rpm-spec", str(spec),
                "--debian-changelog", str(debian_changelog),
            ]

            subprocess.run(command, check=True)
            self.assertIn("Version:        1.2.3", spec.read_text(encoding="utf-8"))
            self.assertIn("- Added: Added native changelog generation.",
                          spec.read_text(encoding="utf-8"))
            self.assertTrue(
                debian_changelog.read_text(encoding="utf-8").startswith(
                    "bwverify (1.2.3-1) unstable; urgency=medium\n"))
            self.assertIn("  * Fixed: Rejected malformed release notes before a package build.",
                          debian_changelog.read_text(encoding="utf-8"))

            generated_spec = spec.read_text(encoding="utf-8")
            generated_debian = debian_changelog.read_text(encoding="utf-8")
            subprocess.run(command, check=True)
            self.assertEqual(spec.read_text(encoding="utf-8"), generated_spec)
            self.assertEqual(debian_changelog.read_text(encoding="utf-8"), generated_debian)

    def test_rejects_invalid_changelog_without_changing_targets(self):
        """Fail before touching package metadata when a category is unsupported."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generator = self.create_project(
                root,
                "# Changelog\n\n## [Unreleased]\n\n## [1.2.3] - 2026-09-20\n\n"
                "### Other\n\n- This category is not supported.\n",
            )
            spec = root / "bwverify.spec"
            debian_changelog = root / "debian.changelog"
            spec_contents = "Name: bwverify\nVersion: 0.0.0\nRelease: 1%{?dist}\n%changelog\n"
            debian_contents = "older entry\n"
            spec.write_text(spec_contents, encoding="utf-8")
            debian_changelog.write_text(debian_contents, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable, str(generator), "--rpm-spec", str(spec),
                    "--debian-changelog", str(debian_changelog),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported category", result.stderr)
            self.assertEqual(spec.read_text(encoding="utf-8"), spec_contents)
            self.assertEqual(debian_changelog.read_text(encoding="utf-8"), debian_contents)

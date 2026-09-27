"""Keep the runnable sample manifests consistent with their documented results."""

import subprocess
import unittest
from pathlib import Path

from bwverify.checksums import calculate_checksum, parse_checksum_file


# Resolve samples from the checkout so their relative manifest paths are exercised directly.
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
REPOSITORY_ROOT = EXAMPLES.parent


# User-facing samples are checked as real manifests, not duplicated test fixtures.
class ExampleManifestTests(unittest.TestCase):
    """Verify real assets using paths relative to each sample manifest."""

    def test_sample_results(self):
        """Match every sample manifest's documented verification outcome."""
        expected_results = {
            "icons.sha256": ["verified"] * 3,
            "icons.sfv": ["verified"] * 3,
            "mixed-results.sha256": ["verified", "mismatched", "missing"],
        }
        # Resolve files exactly where a user opening these manifests expects them.
        for name, expected in expected_results.items():
            with self.subTest(manifest=name):
                results = []
                for entry in parse_checksum_file(EXAMPLES / name):
                    path = EXAMPLES / entry.filename
                    if not path.exists():
                        results.append("missing")
                        continue
                    checksum = calculate_checksum(path, entry.algorithm)
                    results.append("verified" if checksum == entry.checksum else "mismatched")
                self.assertEqual(results, expected)

    def test_make_run_forwards_manifest_argument(self):
        """Pass an optional manifest goal to the local application command."""
        result = subprocess.run(
            ["make", "--dry-run", "--no-print-directory", "run", "examples/icons.sfv"],
            check=True,
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertIn("-m bwverify.bwverify examples/icons.sfv", result.stdout)

    def test_make_windows_runs_the_windows_builder(self):
        """Expose the Windows builder under its platform-specific target name."""
        result = subprocess.run(
            ["make", "--dry-run", "--no-print-directory", "windows"],
            check=True,
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertIn(
            "powershell.exe -ExecutionPolicy Bypass -File scripts/build-windows.ps1",
            result.stdout,
        )

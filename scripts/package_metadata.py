#!/usr/bin/env python3
"""Generate native package changelog entries from the project changelog."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from email.utils import format_datetime
from pathlib import Path
import re
import sys
import tomllib


# Keep the accepted Markdown vocabulary small so package-release parsing is reliable.
CATEGORY_NAMES = (
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
    "Packaging",
)
RELEASE_HEADING = re.compile(
    r"^## \[(?P<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\] - "
    r"(?P<date>\d{4}-\d{2}-\d{2})$"
)
CATEGORY_HEADING = re.compile(r"^### (?P<category>" + "|".join(CATEGORY_NAMES) + r")$")
BULLET = re.compile(r"^- (?P<text>\S.*)$")


class ChangelogSyntaxError(ValueError):
    """Report an invalid project changelog with its line number."""


@dataclass(frozen=True)
class Release:
    """Store one parsed application release."""

    version: str
    release_date: date
    entries: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ProjectMetadata:
    """Store the package and maintainer values needed by native changelogs."""

    package_name: str
    version: str
    maintainer_name: str
    maintainer_email: str


def fail(line_number: int, message: str) -> None:
    """Raise a consistently formatted changelog syntax error."""
    raise ChangelogSyntaxError(f"CHANGELOG.md:{line_number}: {message}")


def parse_release(lines: list[str], heading_index: int, end_index: int) -> Release:
    """Parse one dated release section and reject unsupported Markdown."""
    heading = RELEASE_HEADING.fullmatch(lines[heading_index])
    if heading is None:
        fail(heading_index + 1, "release headings must use '## [X.Y.Z] - YYYY-MM-DD'")

    try:
        release_date = date.fromisoformat(heading["date"])
    except ValueError as error:
        fail(heading_index + 1, f"invalid release date: {error}")

    entries: list[tuple[str, str]] = []
    seen_categories: set[str] = set()
    active_category: str | None = None
    for index in range(heading_index + 1, end_index):
        line = lines[index]
        if not line:
            continue
        category = CATEGORY_HEADING.fullmatch(line)
        if category:
            active_category = category["category"]
            if active_category in seen_categories:
                fail(index + 1, f"duplicate '{active_category}' category")
            seen_categories.add(active_category)
            continue
        bullet = BULLET.fullmatch(line)
        if bullet:
            if active_category is None:
                fail(index + 1, "list entries must follow a category heading")
            entries.append((active_category, bullet["text"]))
            continue
        if line.startswith("### "):
            fail(index + 1, f"unsupported category; use one of: {', '.join(CATEGORY_NAMES)}")
        fail(index + 1, "release entries must be category headings or '- ' list entries")

    if not entries:
        fail(heading_index + 1, "a released version must contain at least one entry")
    return Release(heading["version"], release_date, tuple(entries))


def parse_changelog(path: Path) -> Release:
    """Validate CHANGELOG.md and return its latest published release."""
    # Package builders require an empty Unreleased section to avoid publishing draft notes.
    lines = path.read_text(encoding="utf-8").splitlines()
    section_indexes = [index for index, line in enumerate(lines) if line.startswith("## ")]
    if not section_indexes:
        fail(1, "missing '## [Unreleased]' section")
    if lines[section_indexes[0]] != "## [Unreleased]":
        fail(section_indexes[0] + 1, "the first section must be '## [Unreleased]'")

    unreleased_end = section_indexes[1] if len(section_indexes) > 1 else len(lines)
    if any(line.strip() for line in lines[section_indexes[0] + 1:unreleased_end]):
        fail(section_indexes[0] + 1, "Unreleased must be empty before building a native package")
    if len(section_indexes) < 2:
        fail(section_indexes[0] + 1, "missing a dated release section")

    releases: list[Release] = []
    # The first dated section is the release consumed by native package builders.
    for position, index in enumerate(section_indexes[1:], start=1):
        end_index = (
            section_indexes[position + 1] if position + 1 < len(section_indexes) else len(lines)
        )
        releases.append(parse_release(lines, index, end_index))
    return releases[0]


def read_metadata(path: Path) -> ProjectMetadata:
    """Read the version and maintainer identity from PEP 621 metadata."""
    try:
        # PEP 621 remains the single source for package identity and maintainer details.
        project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        author = project["authors"][0]
        return ProjectMetadata(
            package_name=project["name"].lower(),
            version=project["version"],
            maintainer_name=author["name"],
            maintainer_email=author["email"],
        )
    except (KeyError, IndexError, tomllib.TOMLDecodeError) as error:
        raise ValueError(
            f"pyproject.toml must define project version and first author: {error}") from error


def validate_revision(revision: str) -> None:
    """Keep package revisions simple and valid in both native formats."""
    if not re.fullmatch(r"[1-9]\d*", revision):
        raise ValueError("package revision must be a positive integer")


def rpm_date(release_date: date) -> str:
    """Format a release date in the conventional RPM changelog style."""
    return f"{release_date.strftime('%a %b')} {release_date.day} {release_date:%Y}"


def render_rpm_entry(metadata: ProjectMetadata, release: Release, revision: str) -> str:
    """Render one RPM entry from a published application release."""
    package_version = f"{release.version}-{revision}"
    lines = [
        f"* {rpm_date(release.release_date)} {metadata.maintainer_name} "
        f"<{metadata.maintainer_email}> - {package_version}",
    ]
    lines.extend(f"- {category}: {text}" for category, text in release.entries)
    return "\n".join(lines) + "\n\n"


def update_rpm_spec(path: Path, metadata: ProjectMetadata, release: Release, revision: str) -> None:
    """Update RPM version tags and prepend the release unless it already exists."""
    # Update tags first, then add the matching release exactly once below %changelog.
    contents = path.read_text(encoding="utf-8")
    version_pattern = re.compile(r"^Version:\s*.*$", re.MULTILINE)
    release_pattern = re.compile(r"^Release:\s*.*$", re.MULTILINE)
    if not version_pattern.search(contents) or not release_pattern.search(contents):
        raise ValueError(f"{path}: missing Version or Release tag")
    contents = version_pattern.sub(f"Version:        {metadata.version}", contents, count=1)
    contents = release_pattern.sub(f"Release:        {revision}%{{?dist}}", contents, count=1)

    changelog_marker = re.search(r"^%changelog\s*$", contents, re.MULTILINE)
    if changelog_marker is None:
        raise ValueError(f"{path}: missing %changelog section")
    package_version = f"{release.version}-{revision}"
    entry_pattern = re.compile(rf"^\* .+ - {re.escape(package_version)}$", re.MULTILINE)
    if not entry_pattern.search(contents[changelog_marker.end():]):
        prefix = contents[:changelog_marker.end()]
        suffix = contents[changelog_marker.end():].lstrip("\n")
        contents = f"{prefix}\n{render_rpm_entry(metadata, release, revision)}{suffix}"
    path.write_text(contents, encoding="utf-8")


def render_debian_entry(metadata: ProjectMetadata, release: Release, revision: str) -> str:
    """Render one Debian source-package entry from a published release."""
    package_version = f"{release.version}-{revision}"
    timestamp = datetime.combine(release.release_date, time(), timezone.utc)
    lines = [f"{metadata.package_name} ({package_version}) unstable; urgency=medium", ""]
    lines.extend(f"  * {category}: {text}" for category, text in release.entries)
    lines.extend(("", f" -- {metadata.maintainer_name} <{metadata.maintainer_email}>  "
                      f"{format_datetime(timestamp)}", ""))
    return "\n".join(lines)


def update_debian_changelog(
        path: Path, metadata: ProjectMetadata, release: Release, revision: str) -> None:
    """Prepend the Debian entry unless the source package version already exists."""
    # Debian keeps newest entries first, so a missing entry is prepended rather than appended.
    contents = path.read_text(encoding="utf-8")
    package_version = f"{release.version}-{revision}"
    entry_pattern = re.compile(
        rf"^{re.escape(metadata.package_name)} \({re.escape(package_version)}\) ", re.MULTILINE)
    if not entry_pattern.search(contents):
        contents = render_debian_entry(metadata, release, revision) + contents
    path.write_text(contents, encoding="utf-8")


def parse_arguments() -> argparse.Namespace:
    """Parse target paths selected by the native build wrappers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpm-spec", type=Path, help="RPM spec file to update")
    parser.add_argument("--debian-changelog", type=Path, help="Debian changelog to update")
    parser.add_argument("--revision", default="1", help="native package revision (default: 1)")
    arguments = parser.parse_args()
    if arguments.rpm_spec is None and arguments.debian_changelog is None:
        parser.error("specify --rpm-spec and/or --debian-changelog")
    return arguments


def main() -> int:
    """Validate project release metadata, then update the requested package files."""
    arguments = parse_arguments()
    project_root = Path(__file__).resolve().parents[1]
    # Validate all shared inputs before writing either native package file.
    try:
        validate_revision(arguments.revision)
        metadata = read_metadata(project_root / "pyproject.toml")
        release = parse_changelog(project_root / "CHANGELOG.md")
        if release.version != metadata.version:
            raise ValueError(
                "latest CHANGELOG.md release is "
                f"{release.version}, but pyproject.toml is {metadata.version}")
        if arguments.rpm_spec is not None:
            update_rpm_spec(arguments.rpm_spec, metadata, release, arguments.revision)
        if arguments.debian_changelog is not None:
            update_debian_changelog(
                arguments.debian_changelog, metadata, release, arguments.revision)
    except (ChangelogSyntaxError, OSError, ValueError) as error:
        print(f"Package changelog generation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

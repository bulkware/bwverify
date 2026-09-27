#!/usr/bin/env bash
set -euo pipefail

# Resolve all inputs from the checkout so the wrapper works outside a Git repository.
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
package_revision=${PACKAGE_REVISION:-1}

# Read the version from the local package metadata.
metadata=$(cat "$project_root/pyproject.toml")
version=$(sed -n 's/^[[:space:]]*version = "\([^"]*\)".*/\1/p' <<< "$metadata" |
    head -n 1)

if [[ -z "$version" ]]; then
    echo "Unable to determine the package version from pyproject.toml." >&2
    exit 1
fi

build_root="$project_root/build/rpm/rpmbuild"
# Use a disposable source tree so local caches and configuration cannot enter the archive.
staging_root=$(mktemp -d)
trap 'rm -rf "$staging_root"' EXIT

mkdir -p "$build_root"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
# Stage only package inputs, excluding caches, build output, and local configuration.
source_root="$staging_root/bwverify-$version"
mkdir -p "$source_root/src/bwverify/icons" "$source_root/data" \
    "$source_root/tests" "$source_root/scripts" "$source_root/packaging/rpm" \
    "$source_root/debian" "$source_root/examples"
cp "$project_root/pyproject.toml" "$project_root/README.md" "$project_root/CHANGELOG.md" \
    "$project_root/ICONS.md" "$project_root/LICENSE.md" "$project_root/Makefile" "$source_root/"
cp "$project_root"/src/bwverify/*.py "$source_root/src/bwverify/"
cp "$project_root"/src/bwverify/icons/*.svg "$source_root/src/bwverify/icons/"
# Keep every bundled icon-set directory in the source archive.
for icon_set_directory in "$project_root"/src/bwverify/icons/*/; do
    [[ -d "$icon_set_directory" ]] || continue
    icon_set_name=$(basename "$icon_set_directory")
    mkdir -p "$source_root/src/bwverify/icons/$icon_set_name"
    cp "$icon_set_directory"*.svg "$source_root/src/bwverify/icons/$icon_set_name/"
done
cp "$project_root/data/org.bulkware.bwverify.desktop" \
    "$project_root/data/org.bulkware.bwverify.metainfo.xml" \
    "$project_root/data/org.bulkware.bwverify.xml" "$source_root/data/"
for icon_type in scalable symbolic; do
    icon_path="data/icons/hicolor/$icon_type/apps"
    mkdir -p "$source_root/$icon_path"
    cp "$project_root/$icon_path/"*.svg "$source_root/$icon_path/"
done
cp "$project_root"/tests/*.py "$source_root/tests/"
cp "$project_root"/scripts/*.py "$source_root/scripts/"
cp "$project_root"/scripts/build-rpm.sh "$source_root/scripts/"
cp "$project_root"/packaging/rpm/bwverify.spec "$source_root/packaging/rpm/"
cp "$project_root"/debian/changelog "$source_root/debian/"
cp "$project_root"/examples/* "$source_root/examples/"
tar -czf "$build_root/SOURCES/bwverify-$version.tar.gz" \
    -C "$staging_root" "bwverify-$version"
# Generate native release notes in the staged spec, never in the tracked template.
cp "$project_root/packaging/rpm/bwverify.spec" "$staging_root/bwverify.spec"
python3 "$project_root/scripts/generate_package_changelogs.py" \
    --rpm-spec "$staging_root/bwverify.spec" --revision "$package_revision"
rpmbuild --define "_topdir $build_root" -ba "$staging_root/bwverify.spec"

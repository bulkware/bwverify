#!/usr/bin/env bash
set -euo pipefail

# Build from the checkout because Debian tooling reads the debian/ directory in place.
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
package_revision=${PACKAGE_REVISION:-1}
cd "$project_root"

# Keep the native changelog synchronized with the validated project release notes.
python3 "$project_root/scripts/package_metadata.py" \
    --debian-changelog "$project_root/debian/changelog" --revision "$package_revision"
dpkg-buildpackage -us -uc -b
mkdir -p "$project_root/build/deb"
mv "$project_root"/../bwverify_*.deb "$project_root/build/deb/"

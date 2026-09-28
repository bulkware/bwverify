# bwVerify

A small desktop application for creating and verifying checksum files.

bwVerify is licensed under [GPL-3.0-or-later](LICENSE.md).

## Interface

bwVerify uses GTK 4 directly and does not depend on libadwaita. It is a conventional,
cross-platform desktop utility, so GTK 4 provides the interface it needs without an
extra GNOME-specific runtime dependency.

## Using bwVerify

To create a checksum file, choose **New checksum file**, select a format and path
style, add files or a directory, then save. New documents use SFV with CRC-32 by
default, store paths relative to the checksum file, and suggest `checksums.sfv`.
Files are verified as they are added.

To update an existing checksum file, open it, add files or a directory, then save.
Choose **Verify files** to check a manifest. Opened manifests are checked relative to
their own directory, while new manifests use the paths of the files you added. Each
entry is marked verified, mismatched, missing, or unreadable.

The leading Result column shows each entry's verification icon before its filename,
so results remain visible when a long filename is truncated by the window width.

Absolute paths in an opened manifest remain absolute; relative paths are resolved from
the manifest's directory.

You can open a checksum file from your file manager, run `bwverify checks.sfv`, or
drop a file onto the application window. Select an entry to see its details. The
status line reports progress and completion, and bwVerify remembers the last folder
and window size.

**Main menu (☰) → Preferences** contains Appearance, New checksum files, Saved checksum
files, and Behaviour settings. It controls the theme, icon set, defaults for new
manifests, output encoding and line endings, automatic verification after opening, and
comment removal when saving. UTF-8 and Unix (LF) line endings are the defaults; choose
UTF-8 with BOM, UTF-16, or Western (ISO-8859-1), plus Unix, Windows (CRLF), or classic
Mac (CR) separators as needed. These output choices are used whenever any manifest is
saved, including a file that was opened from disk. The default theme follows the desktop,
falling back to the configured GTK theme on older GTK releases;
choose System, Light, or Dark to override it. Choose bundled Oxygen or Tango artwork, or
GTK Symbolic icons that follow the active theme's foreground colour.

Comments, which often begin with `;` in SFV files, are preserved by default. The compact
Preferences and New checksum file windows have only the controls needed for their task.

### Supported checksum files

- SFV files using CRC-32 records (`filename CRC32`)
- GNU-style MD5, SHA-1, SHA-224, SHA-256, SHA-384, and SHA-512 manifests
  (`digest  filename` or `digest *filename`)
- BSD-style MD5 and SHA manifests (`SHA256 (filename) = digest`)
- Named BSD-style SHA-3 and BLAKE2 manifests

New manifests use SFV with CRC-32 by default. The new-document dialog can also
create GNU-style or BSD-style SHA-256 manifests, and Preferences remembers your
choice. Filenames may be stored relative to the manifest, as full paths, or by name
only. Relative paths are usually the most portable. Name-only manifests work when every
file has a unique name beside the checksum file. When files from different folders are
added to a name-only document, bwVerify switches it to relative paths to avoid ambiguity.

### Integrity is not authenticity

Checksums detect accidental corruption only when the checksum file itself came
from a trusted source. CRC-32, MD5, and SHA-1 are not suitable for proving a
download is authentic. For security-sensitive downloads, obtain the checksum
over a trusted channel or verify the publisher's cryptographic signature first.

### Try the sample checksum files

Run `make run`, open one of these files, then select **Verify files**:

| Checksum file | Expected results |
| --- | --- |
| `examples/icons.sha256` | Three verified icons using SHA-256 |
| `examples/icons.sfv` | The same three verified icons using CRC-32 |
| `examples/mixed-results.sha256` | One verified, one mismatched, and one missing file |

The samples refer to `document-new.svg`, `document-open.svg`, and `dialog-ok.svg` in
`src/bwverify/icons/oxygen/`; leave them in the checkout's `examples/` directory.
`mixed-results.sha256` deliberately includes one bad checksum and one missing file. If
the icon files change, update the successful sample checksums.

## Code layout

`bwverify.py` coordinates the application. Supporting modules keep individual
concerns focused: `models.py` defines GTK list records and icon resources,
`window.py` builds the interface, `document.py` reads and writes manifests, and
`settings.py` stores user preferences in `settings.conf` in the platform user
configuration directory. Existing `settings.ini` files are read once until the
application next saves preferences as `settings.conf`.

The header bar groups document, manifest, and verification actions. The menu on
the right contains the remaining actions, Preferences, and About; **Ctrl+Q** quits.
The packaged icon is registered with GTK so desktops such as Xfce can use it in the
title bar and taskbar. Linux packages also include AppStream and MIME metadata for
the supported checksum-file extensions. Custom application dialogs are regular GTK
windows with explicit controls, keeping the interface current with GTK 4.

## Run from source on Linux

bwVerify requires Python 3.11 or newer.

### Installing dependencies (Fedora)

Install the system PyGObject and GTK 4 packages:

```bash
sudo dnf install python3-gobject gtk4
```

### Installing dependencies (Debian-based systems)

Install Python, the GTK 4 binding, and its runtime:

```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0
```

### Downloading the source

```bash
git clone https://github.com/bulkware/bwverify.git
```

### Running the application

Enter the checkout:

```bash
cd bwverify
```

Then run it from the source tree:

```bash
make run
```

This always uses the local source tree. To open a checksum file immediately,
pass its path after `run`:

```bash
make run examples/icons.sfv
```

To use a different interpreter, run `make run PYTHON=/path/to/python`. Without Make:

```bash
PYTHONPATH=src python3 -m bwverify.bwverify
```

Direct execution also works:

```bash
python3 src/bwverify/bwverify.py
```

## Install from a Python package

After installing the system GTK dependencies, install the package with `pip`:

```bash
python3 -m pip install .
```

The installed command is `bwverify`.

## Building Python packages

To create a source distribution and wheel:

```bash
python -m pip install build
python -m build
```

The artifacts are written to `dist/`.

### Make shortcuts

Run these commands from the checkout root. `make` or `make help` lists every target.

| Command | Purpose |
| --- | --- |
| `make rpm` | Build RPM packages from the local source |
| `make deb` | Build Debian packages from the current working tree |
| `make windows` | Build the Windows portable ZIP and MSI installer |
| `make prepare-release` | Synchronize project and AppStream versions from `CHANGELOG.md` |
| `make install-deb` | Install Debian package build dependencies |
| `make install-rpm` | Install RPM package build dependencies |
| `make build` | Build Python source and wheel distributions in `dist/` |
| `make test` | Run unit tests |
| `make coverage` | Measure application-code test coverage |
| `make lint` | Run PyLint on application code, tests, and the cleanup script |
| `make check` | Run both tests and PyLint |
| `make clean-dry-run` | Preview generated files to remove |
| `make clean` | Remove generated build output and caches |

Run `make check` before a release, then choose the relevant package target.
Package targets do not install dependencies or run checks themselves. `make build`
needs the Python `build` module and `make lint` needs PyLint. You can override the
interpreter, for example with `make check PYTHON=.venv/bin/python`.

### Cleaning generated files

Use `make clean-dry-run` to see what would be removed, then `make clean` to remove
build output, package metadata, bytecode, coverage data, and tool caches. It leaves
source files, virtual environments, local notes, configuration, and Git metadata
alone. Debian artifacts created outside the checkout are also left untouched.

Without Make, including on Windows, run `python scripts/clean.py --dry-run` and
then `python scripts/clean.py`. Rebuild packages after changing source files.

## Development checks

Install the optional development dependency, then run the test suite and PyLint
from the checkout. `PYTHONPATH` lets the commands import the source tree without
installing it first:

```bash
python3 -m pip install -e '.[dev]'
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m coverage run -m unittest discover -s tests -v
python3 -m coverage report -m
PYTHONPATH=src python3 -m pylint --persistent=no src tests scripts/clean.py \
    scripts/package_metadata.py scripts/prepare_release.py src/freeze_entry.py
```

On Fedora, install the system-provided coverage module with:

```bash
sudo dnf install python3-coverage
```

This package is only needed for `make coverage`; `.[dev]` installs the development
tools through `pip` instead.

PyLint follows the project's 100-character line limit and excludes only GTK/GObject
introspection false positives. Tests are display-free and cover controller state,
verification, cancellation, persistence, and packaging metadata. Before a release,
manually check opening, saving, verification, cancellation, preferences,
drag-and-drop, and both themes. Icons remain uncompressed `.svg` files.

## Building for Windows

Windows builds use cx_Freeze to produce a portable ZIP and a per-user MSI. The
documented setup uses the latest released, prebuilt gvsbuild GTK archive and a matching
CPython virtual environment; it does not require MSYS2 or a locally built GTK stack.

From that environment, run the Make target:

```powershell
make windows
```

It invokes the PowerShell build script directly, which remains available when Make
is not installed:

```powershell
scripts\build-windows.ps1
```

Extract the gvsbuild GTK4 x64 archive to `C:\gtk`. It provides the GTK runtime,
PyGObject wheel, and PyCairo wheel used by the build. If GTK is installed elsewhere,
set `GTK_PREFIX` to the directory containing `bin`, `lib`, and `share` before building.

The script stages GTK's runtime, schemas, modules, and icon theme beside the frozen
application. It writes `build\windows\bwverify-<version>-win64-portable.zip` and an
MSI under `build\windows\installer`. Close a previously built `bwVerify.exe` and any
File Explorer window open in its build directory before rebuilding.

cx_Freeze includes the bundled Oxygen/Tango SVG artwork and uses the same staged GTK
runtime in both artifacts.

## Building distribution packages

The project includes native packaging metadata for Debian- and RPM-based
distributions. Build from a checkout with:

```bash
make deb
make rpm
```

The targets call `scripts/build-deb.sh` and `scripts/build-rpm.sh`, which can also
be run directly. Each native builder uses the local source tree; no Git repository or
commit is required. RPM artifacts are placed under `build/rpm/rpmbuild/`.

The Linux builders read the version and first author from `pyproject.toml`, so keep
that metadata valid before building. `make prepare-release` synchronizes the project
version and AppStream release entry from the newest dated changelog section.

The Debian build requires `dpkg-buildpackage`, `debhelper`, `dh-python`,
`pybuild-plugin-pyproject`, and Python build dependencies. Install them with:

```bash
sudo apt install dpkg-dev debhelper dh-python pybuild-plugin-pyproject \
    python3-all python3-setuptools
```

Debian and RPM package builds run the source-tree unit tests and fail if they do not pass.

On Fedora, install the RPM build requirements with:

```bash
sudo dnf install rpm-build pyproject-rpm-macros python3-devel python3-setuptools
```

Both packages use the system PyGObject and GTK 4 runtime.

### Maintaining release notes

`CHANGELOG.md` is the source of release notes for every platform. Add user-visible
items beneath `## [Unreleased]`, using Keep a Changelog categories such as Added,
Changed, Fixed, and Security. Use `Packaging` for installer or package changes;
prefix platform-specific entries with `RPM:`, `Debian:`, or `Windows:`.

For a release, move the entries to `## [X.Y.Z] - YYYY-MM-DD` and recreate an empty
`## [Unreleased]` section. Keep each change as a Markdown list item. Application
versions use Semantic Versioning; native package revisions such as `1.0.0-2` stay
in the packaging metadata.

The Linux build wrappers run `scripts/package_metadata.py` first. It
turns the matching release section into RPM and Debian changelog entries, checks
the heading, categories, and version against `pyproject.toml`, and prevents duplicate
entries. Both wrappers default to package revision `1`; to rebuild the same release
as revision `2`, run `make rpm PACKAGE_REVISION=2` or
`make deb PACKAGE_REVISION=2`. Windows builds use the application version directly.

The test suite also verifies that each seeded RPM and Debian changelog weekday
matches its numeric release date, preventing native-builder warnings.

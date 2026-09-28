"""Configure the bundled GTK runtime before starting the frozen application."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def configure_gtk_runtime() -> None:
    """Prepend paths required by the GTK runtime copied beside the executable."""
    executable_root = Path(sys.executable).resolve().parent
    runtime_root = executable_root / "gtk-runtime"
    if not runtime_root.is_dir():
        return
    paths = {
        "PATH": runtime_root / "bin",
        "GI_TYPELIB_PATH": runtime_root / "lib/girepository-1.0",
        "GTK_PATH": runtime_root / "lib/gtk-4.0",
        "XDG_DATA_DIRS": runtime_root / "share",
        "GSETTINGS_SCHEMA_DIR": runtime_root / "share/glib-2.0/schemas",
    }
    for variable, path in paths.items():
        value = str(path)
        if existing := os.environ.get(variable):
            value = value + os.pathsep + existing
        os.environ[variable] = value


configure_gtk_runtime()

import gi  # pylint: disable=wrong-import-position

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")

from bwverify.bwverify import main  # pylint: disable=wrong-import-position


if __name__ == "__main__":
    main()

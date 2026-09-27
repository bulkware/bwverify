"""GTK list models and icon resources used by bwVerify."""

from importlib import resources

import gi

gi.require_version("GObject", "2.0")
from gi.repository import GObject


# Result names separate controller state from the icon set that renders it.
VERIFIED_ICON_NAME = "bwverify-verified"
UNKNOWN_ICON_NAME = "bwverify-unknown"
WARNING_ICON_NAME = "bwverify-warning"
ERROR_ICON_NAME = "bwverify-error"

# Resolve bundled artwork through package resources so installed builds need no cwd.
ICON_DIRECTORY = resources.files("bwverify").joinpath("icons")
OXYGEN_ICON_DIRECTORY = ICON_DIRECTORY.joinpath("oxygen")
TANGO_ICON_DIRECTORY = ICON_DIRECTORY.joinpath("tango")
MENU_LIGHT_ICON_PATH = str(ICON_DIRECTORY.joinpath("menu-light.svg"))
MENU_DARK_ICON_PATH = str(ICON_DIRECTORY.joinpath("menu-dark.svg"))
VERIFIED_ICON_PATH = str(OXYGEN_ICON_DIRECTORY.joinpath("dialog-ok.svg"))
ICON_SETS = ("oxygen", "symbolic", "tango")

# Oxygen paths keep the application's traditional full-colour presentation.
OXYGEN_HEADER_ICONS = {
    "open": str(OXYGEN_ICON_DIRECTORY.joinpath("document-open.svg")),
    "new": str(OXYGEN_ICON_DIRECTORY.joinpath("document-new.svg")),
    "add-files": str(OXYGEN_ICON_DIRECTORY.joinpath("list-add.svg")),
    "add-directory": str(OXYGEN_ICON_DIRECTORY.joinpath("folder-new.svg")),
    "save": str(OXYGEN_ICON_DIRECTORY.joinpath("document-save.svg")),
    "close": str(OXYGEN_ICON_DIRECTORY.joinpath("document-close.svg")),
    "cancel": str(OXYGEN_ICON_DIRECTORY.joinpath("process-stop.svg")),
    "verify": VERIFIED_ICON_PATH,
}
OXYGEN_RESULT_ICONS = {
    VERIFIED_ICON_NAME: VERIFIED_ICON_PATH,
    UNKNOWN_ICON_NAME: str(OXYGEN_ICON_DIRECTORY.joinpath("dialog-information.svg")),
    WARNING_ICON_NAME: str(OXYGEN_ICON_DIRECTORY.joinpath("dialog-warning.svg")),
    ERROR_ICON_NAME: str(OXYGEN_ICON_DIRECTORY.joinpath("dialog-error.svg")),
    "process-working-symbolic": str(OXYGEN_ICON_DIRECTORY.joinpath("view-refresh.svg")),
}

# Tango paths provide a second bundled full-colour presentation.
TANGO_HEADER_ICONS = {
    "open": str(TANGO_ICON_DIRECTORY.joinpath("document-open.svg")),
    "new": str(TANGO_ICON_DIRECTORY.joinpath("document-new.svg")),
    "add-files": str(TANGO_ICON_DIRECTORY.joinpath("list-add.svg")),
    "add-directory": str(TANGO_ICON_DIRECTORY.joinpath("folder-new.svg")),
    "save": str(TANGO_ICON_DIRECTORY.joinpath("document-save.svg")),
    "close": str(TANGO_ICON_DIRECTORY.joinpath("text-x-generic-attention.svg")),
    "cancel": str(TANGO_ICON_DIRECTORY.joinpath("process-stop.svg")),
    "verify": str(TANGO_ICON_DIRECTORY.joinpath("dialog-accept.svg")),
}
TANGO_RESULT_ICONS = {
    VERIFIED_ICON_NAME: str(TANGO_ICON_DIRECTORY.joinpath("dialog-accept.svg")),
    UNKNOWN_ICON_NAME: str(TANGO_ICON_DIRECTORY.joinpath("dialog-information.svg")),
    WARNING_ICON_NAME: str(TANGO_ICON_DIRECTORY.joinpath("dialog-warning.svg")),
    ERROR_ICON_NAME: str(TANGO_ICON_DIRECTORY.joinpath("dialog-error.svg")),
    "process-working-symbolic": str(TANGO_ICON_DIRECTORY.joinpath("view-refresh.svg")),
}

# Theme icon names provide a compact, recolourable alternative to Oxygen artwork.
SYMBOLIC_HEADER_ICONS = {
    "open": "document-open-symbolic",
    "new": "document-new-symbolic",
    "add-files": "list-add-symbolic",
    "add-directory": "folder-new-symbolic",
    "save": "document-save-symbolic",
    "close": "window-close-symbolic",
    "cancel": "process-stop-symbolic",
    "verify": "checkbox-checked-symbolic",
}
SYMBOLIC_RESULT_ICONS = {
    VERIFIED_ICON_NAME: "checkbox-checked-symbolic",
    UNKNOWN_ICON_NAME: "dialog-information-symbolic",
    WARNING_ICON_NAME: "dialog-warning-symbolic",
    ERROR_ICON_NAME: "dialog-error-symbolic",
    "process-working-symbolic": "process-working-symbolic",
}


def header_icon(icon_set, name, prefers_dark=False):
    """Return the configured icon source for a header-bar control."""
    if name == "menu":
        # The custom menu artwork needs an explicit contrast variant per theme.
        return MENU_DARK_ICON_PATH if prefers_dark else MENU_LIGHT_ICON_PATH
    icon_maps = {
        "symbolic": SYMBOLIC_HEADER_ICONS,
        "tango": TANGO_HEADER_ICONS,
    }
    icon_map = icon_maps.get(icon_set, OXYGEN_HEADER_ICONS)
    return icon_map[name]


def result_icon(icon_set, name):
    """Return the configured icon source for a verification result."""
    icon_maps = {
        "symbolic": SYMBOLIC_RESULT_ICONS,
        "tango": TANGO_RESULT_ICONS,
    }
    # Preserve GTK's transient icon name if it has no bundled equivalent.
    icon_map = icon_maps.get(icon_set, OXYGEN_RESULT_ICONS)
    return icon_map.get(name, name)


class FileItem(GObject.Object):
    """One checksum-file record displayed in the file list."""

    # Bindable properties keep GTK list rows synchronized with worker results.
    filename = GObject.Property(type=str, default="")
    checksum = GObject.Property(type=str, default="")
    algorithm = GObject.Property(type=str, default="")
    status = GObject.Property(type=str, default="Unknown")
    icon_name = GObject.Property(type=str, default=UNKNOWN_ICON_NAME)
    actual_checksum = GObject.Property(type=str, default="")
    detail = GObject.Property(type=str, default="")
    source_path = GObject.Property(type=str, default="")

    def __init__(self, filename, checksum, algorithm):
        super().__init__(filename=filename, checksum=checksum, algorithm=algorithm)

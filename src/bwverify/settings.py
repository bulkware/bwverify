"""Persistent user settings for bwVerify."""

import configparser
from dataclasses import dataclass
import os

from bwverify.document import (
    DEFAULT_FILE_ENCODING,
    DEFAULT_LINE_ENDING,
    DEFAULT_NEW_DOCUMENT_FORMAT,
    DEFAULT_NEW_DOCUMENT_PATH_MODE,
    file_encoding,
    line_ending,
    new_document_format,
    new_document_path_mode,
)


@dataclass
class ApplicationSettings:
    """Settings retained between application launches."""

    window_width: int = 800
    window_height: int = 600
    last_directory: str | None = None
    auto_verify_after_open: bool = False
    remove_comments_on_save: bool = False
    default_checksum_format: str = DEFAULT_NEW_DOCUMENT_FORMAT
    default_path_mode: str = DEFAULT_NEW_DOCUMENT_PATH_MODE
    theme: str = "system"
    icon_set: str = "oxygen"
    file_encoding: str = DEFAULT_FILE_ENCODING
    line_ending: str = DEFAULT_LINE_ENDING


def load_settings(path, legacy_path=None):
    """Load settings, falling back to *legacy_path* when the new file is absent."""
    # Start from safe defaults so malformed or partial configuration never blocks launch.
    settings = configparser.ConfigParser()
    values = ApplicationSettings()
    source_path = path
    # Prefer a present new-format file, even if it is incomplete, over stale legacy values.
    if legacy_path and not os.path.exists(path):
        source_path = legacy_path
    try:
        settings.read(source_path, encoding="utf-8")
        values.window_width = settings.getint("window", "width", fallback=800)
        values.window_height = settings.getint("window", "height", fallback=600)
        values.last_directory = settings.get("files", "last_directory", fallback=None)
        values.auto_verify_after_open = settings.getboolean(
            "preferences", "auto_verify_after_open", fallback=False
        )
        values.remove_comments_on_save = settings.getboolean(
            "preferences", "remove_comments_on_save", fallback=False
        )
        # Validate persisted identifiers against the current choices before retaining them.
        configured_format = settings.get(
            "preferences", "default_checksum_format", fallback=DEFAULT_NEW_DOCUMENT_FORMAT
        )
        values.default_checksum_format = new_document_format(configured_format).identifier
        configured_path_mode = settings.get(
            "preferences", "default_path_mode", fallback=DEFAULT_NEW_DOCUMENT_PATH_MODE
        )
        values.default_path_mode = new_document_path_mode(configured_path_mode).identifier
        configured_theme = settings.get("preferences", "theme", fallback="system")
        if configured_theme in ("system", "light", "dark"):
            values.theme = configured_theme
        configured_icon_set = settings.get("preferences", "icon_set", fallback="oxygen")
        if configured_icon_set in ("oxygen", "symbolic", "tango"):
            values.icon_set = configured_icon_set
        configured_encoding = settings.get(
            "preferences", "file_encoding", fallback=DEFAULT_FILE_ENCODING
        )
        values.file_encoding = file_encoding(configured_encoding).identifier
        configured_line_ending = settings.get(
            "preferences", "line_ending", fallback=DEFAULT_LINE_ENDING
        )
        values.line_ending = line_ending(configured_line_ending).identifier
    except (OSError, ValueError, configparser.Error):
        pass
    return values


def save_settings(path, values):
    """Store *values* at *path* and silently ignore unavailable config storage."""
    # Write groups explicitly to keep the on-disk format readable and stable.
    settings = configparser.ConfigParser()
    settings["window"] = {
        "width": str(max(values.window_width, 1)),
        "height": str(max(values.window_height, 1)),
    }
    if values.last_directory:
        settings["files"] = {"last_directory": values.last_directory}
    settings["preferences"] = {
        "auto_verify_after_open": str(values.auto_verify_after_open),
        "remove_comments_on_save": str(values.remove_comments_on_save),
        "default_checksum_format": new_document_format(
            values.default_checksum_format
        ).identifier,
        "default_path_mode": new_document_path_mode(values.default_path_mode).identifier,
        "theme": values.theme if values.theme in ("system", "light", "dark") else "system",
        "icon_set": values.icon_set
        if values.icon_set in ("oxygen", "symbolic", "tango")
        else "oxygen",
        "file_encoding": file_encoding(values.file_encoding).identifier,
        "line_ending": line_ending(values.line_ending).identifier,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            settings.write(handle)
    except OSError:
        pass

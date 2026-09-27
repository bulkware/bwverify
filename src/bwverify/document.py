"""Checksum-document loading and saving helpers."""

import os
from dataclasses import dataclass

from bwverify.checksums import (
    ChecksumEntry,
    manifest_comments_and_style,
    parse_checksum_file,
    write_checksum_file,
)


@dataclass(frozen=True)
class NewDocumentFormat:
    """One supported format preset for a newly created checksum document."""

    identifier: str
    label: str
    style: str
    algorithm: str
    suggested_filename: str


# Keep new-document choices small and interoperable while making the record
# syntax and the required checksum algorithm unambiguous.
NEW_DOCUMENT_FORMATS = (
    NewDocumentFormat("sfv", "SFV (CRC-32)", "sfv", "CRC-32", "checksums.sfv"),
    NewDocumentFormat("gnu-sha256", "GNU-style (SHA-256)", "gnu", "SHA-256", "checksums.sha256"),
    NewDocumentFormat("bsd-sha256", "BSD-style (SHA-256)", "bsd", "SHA-256", "checksums.sha256"),
)

DEFAULT_NEW_DOCUMENT_FORMAT = "sfv"


def new_document_format(identifier):
    """Return a valid new-document preset, falling back to the SFV default."""
    for document_format in NEW_DOCUMENT_FORMATS:
        if document_format.identifier == identifier:
            return document_format
    return NEW_DOCUMENT_FORMATS[0]


@dataclass(frozen=True)
class NewDocumentPathMode:
    """One supported way to store source filenames in a new document."""

    identifier: str
    label: str


# A checksum record always needs a filename. The filename-only option omits
# directory components and is therefore best suited to unique, sibling files.
NEW_DOCUMENT_PATH_MODES = (
    NewDocumentPathMode("relative", "Relative to checksum file"),
    NewDocumentPathMode("absolute", "Full paths"),
    NewDocumentPathMode("filename", "File names only"),
)
DEFAULT_NEW_DOCUMENT_PATH_MODE = "relative"


def new_document_path_mode(identifier):
    """Return a valid path-storage mode, falling back to relative paths."""
    for path_mode in NEW_DOCUMENT_PATH_MODES:
        if path_mode.identifier == identifier:
            return path_mode
    return NEW_DOCUMENT_PATH_MODES[0]


@dataclass(frozen=True)
class FileEncoding:
    """One supported character encoding for saved checksum documents."""

    identifier: str
    label: str


# UTF-16 uses a byte-order marker so saved manifests can be decoded reliably on open.
FILE_ENCODINGS = (
    FileEncoding("utf-8", "UTF-8"),
    FileEncoding("utf-8-sig", "UTF-8 with BOM"),
    FileEncoding("utf-16", "UTF-16"),
    FileEncoding("latin-1", "Western (ISO-8859-1)"),
)
DEFAULT_FILE_ENCODING = "utf-8"


def file_encoding(identifier):
    """Return a supported file encoding, falling back to UTF-8."""
    for encoding in FILE_ENCODINGS:
        if encoding.identifier == identifier:
            return encoding
    return FILE_ENCODINGS[0]


@dataclass(frozen=True)
class LineEnding:
    """One supported record separator for saved checksum documents."""

    identifier: str
    label: str
    value: str


# Keep Unix LF as the portable default while offering common platform alternatives.
LINE_ENDINGS = (
    LineEnding("lf", "Unix (LF)", "\n"),
    LineEnding("crlf", "Windows (CRLF)", "\r\n"),
    LineEnding("cr", "Classic Mac (CR)", "\r"),
)
DEFAULT_LINE_ENDING = "lf"


def line_ending(identifier):
    """Return a supported line ending, falling back to Unix LF."""
    for ending in LINE_ENDINGS:
        if ending.identifier == identifier:
            return ending
    return LINE_ENDINGS[0]


@dataclass(frozen=True)
class LoadedDocument:
    """The parsed records and formatting metadata of a checksum document."""

    entries: list[ChecksumEntry]
    comments: list[str]
    style: str


def load_document(filepath):
    """Read manifest entries and formatting metadata from *filepath*."""
    entries = parse_checksum_file(filepath)
    comments, style = manifest_comments_and_style(filepath)
    return LoadedDocument(entries, comments, style)


def save_new_document(
    filepath,
    records,
    style="gnu",
    path_mode="relative",
    encoding=DEFAULT_FILE_ENCODING,
    line_ending_identifier=DEFAULT_LINE_ENDING,
):
    """Write source records with the selected path mode and return their entries."""
    # Convert source paths only when saving so unsaved documents remain verifiable.
    output_directory = os.path.dirname(filepath)
    selected_path_mode = new_document_path_mode(path_mode).identifier

    def stored_filename(path):
        """Return the path representation selected for one source file."""
        if selected_path_mode == "absolute":
            return os.path.abspath(path)
        if selected_path_mode == "filename":
            return os.path.basename(path)
        # Relative paths are anchored at the eventual manifest location, not the cwd.
        return os.path.relpath(path, output_directory)

    entries = [
        ChecksumEntry(stored_filename(path), checksum, algorithm)
        for path, checksum, algorithm in records
    ]
    write_checksum_file(
        filepath,
        entries,
        style,
        encoding=file_encoding(encoding).identifier,
        line_ending=line_ending(line_ending_identifier).value,
    )
    return entries


def save_open_document(
    filepath,
    entries,
    style,
    comments,
    encoding=DEFAULT_FILE_ENCODING,
    line_ending_identifier=DEFAULT_LINE_ENDING,
):
    """Write an opened manifest while preserving its selected style and comments."""
    write_checksum_file(
        filepath,
        entries,
        style,
        comments,
        encoding=file_encoding(encoding).identifier,
        line_ending=line_ending(line_ending_identifier).value,
    )

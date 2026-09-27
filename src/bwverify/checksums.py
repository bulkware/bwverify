"""Checksum-manifest parsing and streaming checksum calculation helpers."""

import codecs
from dataclasses import dataclass
import hashlib
import locale
import os
import re
import zlib


# Read large files incrementally to keep verification memory usage predictable.
CHUNK_SIZE = 1024 * 1024

# Digest lengths identify traditional manifest records that omit an algorithm name.
ALGORITHM_BY_LENGTH = {
    8: "CRC-32",
    32: "MD5",
    40: "SHA-1",
    56: "SHA-224",
    64: "SHA-256",
    96: "SHA-384",
    128: "SHA-512",
}
# hashlib uses identifiers that differ slightly from names shown in the interface.
HASHLIB_NAMES = {
    "MD5": "md5",
    "SHA-1": "sha1",
    "SHA-224": "sha224",
    "SHA-256": "sha256",
    "SHA-384": "sha384",
    "SHA-512": "sha512",
    "SHA3-224": "sha3_224",
    "SHA3-256": "sha3_256",
    "SHA3-384": "sha3_384",
    "SHA3-512": "sha3_512",
    "BLAKE2B": "blake2b",
    "BLAKE2S": "blake2s",
}
# Explicitly named BSD records still need digest-length validation before use.
DIGEST_LENGTHS = {
    algorithm: length
    for length, algorithm in ALGORITHM_BY_LENGTH.items()
}
DIGEST_LENGTHS.update(
    {
        "SHA3-224": 56,
        "SHA3-256": 64,
        "SHA3-384": 96,
        "SHA3-512": 128,
        "BLAKE2B": 128,
        "BLAKE2S": 64,
    }
)
# Normalise BSD labels to the application names used throughout the document model.
BSD_ALGORITHMS = {
    "MD5": "MD5",
    "SHA1": "SHA-1",
    "SHA224": "SHA-224",
    "SHA256": "SHA-256",
    "SHA384": "SHA-384",
    "SHA512": "SHA-512",
    "SHA3-224": "SHA3-224",
    "SHA3-256": "SHA3-256",
    "SHA3-384": "SHA3-384",
    "SHA3-512": "SHA3-512",
    "BLAKE2B": "BLAKE2B",
    "BLAKE2S": "BLAKE2S",
}
# Compile supported record formats once because every manifest line uses them.
SFV_RECORD = re.compile(r"^(?P<filename>.+?)\s+(?P<checksum>[0-9a-fA-F]{8})\s*$")
BSD_RECORD = re.compile(
    r"^(?P<algorithm>MD5|SHA1|SHA224|SHA256|SHA384|SHA512|"
    r"SHA3-(?:224|256|384|512)|BLAKE2[BS]) "
    r"\((?P<filename>.*)\) = (?P<checksum>[0-9a-fA-F]+)\s*$",
    re.IGNORECASE,
)
# GNU checksum utilities use two spaces for text-mode entries or `` *`` for
# binary-mode entries. Keeping the separator explicit prevents an SFV filename
# containing eight hexadecimal characters from being interpreted backwards.
GNU_RECORD = re.compile(
    r"^(?P<escaped>\\)?(?P<checksum>[0-9a-fA-F]+)(?:  (?P<text_filename>.+)| "
    r"\*(?P<binary_filename>.+))$"
)


class ChecksumFileError(ValueError):
    """Raised when a checksum manifest cannot be read or parsed."""


class VerificationCancelled(Exception):
    """Raised when a running checksum calculation is cancelled."""


@dataclass(frozen=True)
class ChecksumEntry:
    """A filename, expected digest, and checksum algorithm."""

    filename: str
    checksum: str
    algorithm: str


def algorithm_for_checksum(checksum):
    """Return the known algorithm for a hexadecimal digest, if any."""
    return ALGORITHM_BY_LENGTH.get(len(checksum))


def parse_checksum_file(filepath):
    """Return entries from an SFV, GNU-style, or BSD-style checksum manifest.

    Supported formats are SFV records (``filename CRC32``), GNU coreutils
    checksum records (``digest [ *]filename``), and BSD records such as
    ``SHA256 (filename) = digest``. Blank lines and semicolon comments are
    ignored.
    """
    # Collect all malformed line numbers so users can fix a manifest in one pass.
    entries = []
    invalid_lines = []

    try:
        with open(filepath, "rb") as handle:
            contents = decode_manifest(handle.read())
        for line_number, line in enumerate(contents.splitlines(), start=1):
            text = line.rstrip("\r\n")
            if not text.strip() or text.lstrip().startswith((";", "#")):
                continue

            try:
                entries.append(parse_checksum_record(text))
            except ChecksumFileError:
                invalid_lines.append(str(line_number))
    except OSError as error:
        raise ChecksumFileError(f"Unable to read checksum file: {error}") from error

    if invalid_lines:
        raise ChecksumFileError(
            f"Invalid checksum record on line(s): {', '.join(invalid_lines)}."
        )
    if not entries:
        raise ChecksumFileError("The checksum file contains no supported records.")

    return entries


def manifest_comments_and_style(filepath):
    """Return comment lines and the record style used by a checksum manifest."""
    # Preserve leading comments and infer the first record's syntax for safe saves.
    comments = []
    style = "gnu"
    try:
        with open(filepath, "rb") as handle:
            contents = decode_manifest(handle.read())
    except OSError as error:
        raise ChecksumFileError(f"Unable to read checksum file: {error}") from error

    for line in contents.splitlines():
        text = line.rstrip("\r\n")
        if text.lstrip().startswith((";", "#")):
            comments.append(text)
            continue
        if not text.strip():
            continue
        if BSD_RECORD.match(text):
            style = "bsd"
        elif SFV_RECORD.match(text):
            style = "sfv"
        break
    return comments, style


def parse_sfv_file(filepath):
    """Return CRC-32 entries from an SFV file for backwards-compatible callers."""
    entries = parse_checksum_file(filepath)
    if any(entry.algorithm != "CRC-32" for entry in entries):
        raise ChecksumFileError("The checksum file contains non-SFV records.")
    return entries


def parse_checksum_record(text):
    """Parse one supported checksum record."""
    # Test unambiguous named formats before the more permissive SFV expression.
    bsd_match = BSD_RECORD.match(text)
    if bsd_match is not None:
        algorithm = BSD_ALGORITHMS[bsd_match.group("algorithm").upper()]
        return make_entry(
            bsd_match.group("filename"), bsd_match.group("checksum"), algorithm
        )

    gnu_match = GNU_RECORD.match(text)
    if gnu_match is not None:
        filename = gnu_match.group("text_filename") or gnu_match.group("binary_filename")
        if gnu_match.group("escaped"):
            filename = unescape_gnu_filename(filename)
        return make_entry(filename, gnu_match.group("checksum"))

    sfv_match = SFV_RECORD.match(text)
    if sfv_match is not None:
        return make_entry(
            sfv_match.group("filename"), sfv_match.group("checksum"), "CRC-32"
        )

    raise ChecksumFileError("Unsupported checksum record.")


def make_entry(filename, checksum, algorithm=None):
    """Create a validated checksum entry."""
    checksum = checksum.upper()
    detected_algorithm = algorithm_for_checksum(checksum)
    if not filename or (algorithm is None and detected_algorithm is None):
        raise ChecksumFileError("Unsupported checksum record.")
    if algorithm is not None and DIGEST_LENGTHS.get(algorithm) != len(checksum):
        raise ChecksumFileError("Checksum length does not match its algorithm.")
    return ChecksumEntry(filename, checksum, algorithm or detected_algorithm)


def decode_manifest(contents):
    """Decode supported manifest encodings with UTF-8 as the normal default."""
    # UTF-16 saves include a marker, allowing them to be reopened without a setting.
    if contents.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        try:
            return contents.decode("utf-16")
        except UnicodeDecodeError:
            pass
    # ``dict.fromkeys`` avoids retrying the same codec when the locale is UTF-8.
    encodings = ("utf-8-sig", locale.getpreferredencoding(False), "latin-1")
    for encoding in dict.fromkeys(encodings):
        try:
            return contents.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ChecksumFileError("Unable to decode checksum file.")


def unescape_gnu_filename(filename):
    """Decode the backslash escapes used by GNU checksum utilities."""
    # GNU manifests define escapes only for backslashes and line endings.
    result = []
    index = 0
    while index < len(filename):
        character = filename[index]
        if character != "\\" or index + 1 == len(filename):
            result.append(character)
            index += 1
            continue
        escaped = filename[index + 1]
        result.append({"n": "\n", "r": "\r", "\\": "\\"}.get(escaped, "\\" + escaped))
        index += 2
    return "".join(result)


def escape_gnu_filename(filename):
    """Return a GNU checksum filename and whether its record needs a prefix."""
    escaped = filename.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
    return escaped, escaped != filename


def format_checksum_record(entry, style="gnu"):
    """Format one entry as an SFV, GNU, or BSD checksum record."""
    if style == "sfv":
        if entry.algorithm != "CRC-32":
            raise ValueError("SFV files require CRC-32 checksums.")
        return f"{entry.filename} {entry.checksum}"
    if style == "bsd":
        name = (
            entry.algorithm.replace("-", "")
            if entry.algorithm.startswith("SHA-")
            else entry.algorithm
        )
        return f"{name} ({entry.filename}) = {entry.checksum}"
    if style == "gnu":
        # The leading backslash tells GNU readers that filename escaping was used.
        filename, escaped = escape_gnu_filename(entry.filename)
        return f"{'\\' if escaped else ''}{entry.checksum} *{filename}"
    raise ValueError(f"Unsupported manifest style: {style}")


def write_checksum_file(
    filepath,
    entries,
    style="gnu",
    comments=(),
    encoding="utf-8",
    line_ending="\n",
):
    """Write entries and comments atomically with the requested encoding and line ending."""
    # Write beside the destination, then replace it only after all output succeeds.
    temporary_path = f"{filepath}.tmp"
    try:
        with open(temporary_path, "w", encoding=encoding, newline="") as handle:
            for comment in comments:
                handle.write(comment.rstrip("\r\n"))
                handle.write(line_ending)
            for entry in entries:
                handle.write(format_checksum_record(entry, style))
                handle.write(line_ending)
        os.replace(temporary_path, filepath)
    except (OSError, UnicodeError) as error:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise ChecksumFileError(f"Unable to write checksum file: {error}") from error


def calculate_checksum(filepath, algorithm, should_cancel=None):
    """Calculate a file checksum without loading the whole file into memory."""
    # CRC-32 is implemented by zlib, while the remaining supported digests use hashlib.
    if algorithm == "CRC-32":
        return calculate_crc32(filepath, should_cancel)

    try:
        digest = hashlib.new(HASHLIB_NAMES[algorithm])
    except KeyError as error:
        raise ValueError(f"Unsupported checksum algorithm: {algorithm}") from error

    with open(filepath, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            check_cancelled(should_cancel)
            digest.update(chunk)
    return digest.hexdigest().upper()


def calculate_crc32(filepath, should_cancel=None):
    """Calculate a file's CRC-32 checksum without loading it all into memory."""
    checksum = 0
    with open(filepath, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            check_cancelled(should_cancel)
            checksum = zlib.crc32(chunk, checksum)
    return f"{checksum & 0xFFFFFFFF:08X}"


def check_cancelled(should_cancel):
    """Raise when the optional cancellation callback requests a stop."""
    if should_cancel is not None and should_cancel():
        raise VerificationCancelled()

"""Keep desktop-entry, MIME, and AppStream metadata internally consistent."""

from pathlib import Path
from datetime import datetime
import re
import unittest
from xml.etree import ElementTree


# Keep all desktop-integration fixtures rooted in the installed metadata directory.
DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"
MIME_NAMESPACE = "{http://www.freedesktop.org/standards/shared-mime-info}"
MANIFEST_MIME_TYPES = {
    "application/x-sfv",
    "application/x-bwverify-md5",
    "application/x-bwverify-sha1",
    "application/x-bwverify-sha224",
    "application/x-bwverify-sha256",
    "application/x-bwverify-sha384",
    "application/x-bwverify-sha512",
}


# These checks prevent MIME registration and the desktop launcher from drifting apart.
class DesktopMetadataTests(unittest.TestCase):
    """Ensure installed desktop metadata describes the supported manifests."""

    def test_desktop_entry_references_every_packaged_mime_type(self):
        """Each registered checksum MIME type opens bwVerify from a file manager."""
        desktop_entry = (DATA_DIRECTORY / "org.bulkware.bwverify.desktop").read_text(
            encoding="utf-8"
        )
        mime_line = next(
            line for line in desktop_entry.splitlines() if line.startswith("MimeType=")
        )
        desktop_mime_types = set(mime_line.removeprefix("MimeType=").split(";"))
        desktop_mime_types.discard("")

        self.assertEqual(desktop_mime_types, MANIFEST_MIME_TYPES)

    def test_mime_definitions_and_appstream_identity_match_the_desktop_entry(self):
        """Package metadata has one application identity and all manifest definitions."""
        mime_tree = ElementTree.parse(DATA_DIRECTORY / "org.bulkware.bwverify.xml")
        mime_types = {
            element.attrib["type"]
            for element in mime_tree.findall(f"{MIME_NAMESPACE}mime-type")
        }
        appstream_tree = ElementTree.parse(DATA_DIRECTORY / "org.bulkware.bwverify.metainfo.xml")

        self.assertEqual(mime_types, MANIFEST_MIME_TYPES)
        self.assertEqual(appstream_tree.findtext("id"), "org.bulkware.bwverify")
        self.assertEqual(
            appstream_tree.findtext("launchable"),
            "org.bulkware.bwverify.desktop",
        )

    def test_native_template_changelog_weekdays_match_their_dates(self):
        """Keep manually seeded native changelog entries valid for their builders."""
        root = DATA_DIRECTORY.parent
        rpm = (root / "packaging/rpm/bwverify.spec").read_text(encoding="utf-8")
        debian = (root / "debian/changelog").read_text(encoding="utf-8")
        rpm_match = re.search(r"^\* (?P<weekday>\w{3}) (?P<date>\w{3} \d{1,2} \d{4}) ",
                              rpm, re.MULTILINE)
        debian_match = re.search(r"^ -- .+  (?P<weekday>\w{3}), (?P<date>\d{1,2} \w{3} \d{4}) ",
                                 debian, re.MULTILINE)

        self.assertIsNotNone(rpm_match)
        self.assertIsNotNone(debian_match)
        rpm_date = datetime.strptime(rpm_match["date"], "%b %d %Y")
        debian_date = datetime.strptime(debian_match["date"], "%d %b %Y")
        self.assertEqual(rpm_match["weekday"], rpm_date.strftime("%a"))
        self.assertEqual(debian_match["weekday"], debian_date.strftime("%a"))

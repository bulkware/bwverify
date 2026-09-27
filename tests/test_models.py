"""Tests for selecting compatible icon sources without a graphical display."""

import unittest

from bwverify.models import (
    ERROR_ICON_NAME,
    UNKNOWN_ICON_NAME,
    header_icon,
    result_icon,
)


# Icon-source selection is pure logic and stays safe to test without a display server.
class IconSelectionTests(unittest.TestCase):
    """Ensure both supported icon presentations cover all application states."""

    def test_oxygen_uses_bundled_svg_assets_for_previously_theme_only_icons(self):
        """Oxygen includes save, menu, and working-state artwork from the supplied set."""
        self.assertTrue(header_icon("oxygen", "save").endswith("document-save.svg"))
        self.assertTrue(header_icon("oxygen", "menu").endswith("menu-light.svg"))
        self.assertTrue(
            result_icon("oxygen", "process-working-symbolic").endswith("view-refresh.svg")
        )

    def test_symbolic_uses_recolourable_gtk_icon_names(self):
        """Symbolic maps toolbar and result states to active-theme icon names."""
        self.assertEqual(header_icon("symbolic", "save"), "document-save-symbolic")
        self.assertEqual(header_icon("symbolic", "verify"), "checkbox-checked-symbolic")
        self.assertTrue(
            header_icon("symbolic", "menu", prefers_dark=True).endswith("menu-dark.svg")
        )
        self.assertEqual(result_icon("symbolic", UNKNOWN_ICON_NAME), "dialog-information-symbolic")
        self.assertEqual(result_icon("symbolic", ERROR_ICON_NAME), "dialog-error-symbolic")

    def test_tango_uses_the_staged_close_and_accept_icons(self):
        """Tango maps the supplied unofficial additions to their intended states."""
        self.assertTrue(
            header_icon("tango", "close").endswith("text-x-generic-attention.svg")
        )
        self.assertTrue(header_icon("tango", "verify").endswith("dialog-accept.svg"))
        self.assertTrue(result_icon("tango", ERROR_ICON_NAME).endswith("dialog-error.svg"))

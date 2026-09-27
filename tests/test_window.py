"""Check primary-menu navigation without requiring a display server."""

import unittest

from bwverify.window import TABLE_COLUMNS, create_primary_menu


# Menu construction is data-driven, so it can be validated without presenting a window.
class PrimaryMenuTests(unittest.TestCase):
    """Ensure the menu exposes existing actions in flat task groups."""

    def test_action_groups(self):
        """Expose the application's actions in the expected flat menu groups."""
        menu = create_primary_menu()
        expected_groups = (
            ["app.new", "app.open", "app.close-file"],
            ["app.add-files", "app.add-directory", "app.save"],
            ["app.verify", "app.cancel"],
            ["app.preferences", "app.about"],
        )
        self.assertEqual(menu.get_n_items(), len(expected_groups))
        # Check public menu links so nested submenus cannot hide these actions.
        for index, expected in enumerate(expected_groups):
            self.assertIsNone(menu.get_item_link(index, "submenu"))
            section = menu.get_item_link(index, "section")
            self.assertIsNotNone(section)
            actions = []
            for item in range(section.get_n_items()):
                self.assertIsNone(section.get_item_link(item, "submenu"))
                self.assertTrue(section.get_item_attribute_value(item, "label", None).unpack())
                actions.append(section.get_item_attribute_value(item, "action", None).unpack())
            self.assertEqual(actions, expected)


class TableLayoutTests(unittest.TestCase):
    """Ensure key verification feedback stays visible in narrow table views."""

    def test_result_column_precedes_the_file_column(self):
        """Keep result icons visible when GTK truncates a long filename."""
        self.assertEqual(TABLE_COLUMNS[0], ("Result", None))
        self.assertEqual(TABLE_COLUMNS[1], ("File", "filename"))

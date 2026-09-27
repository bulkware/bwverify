"""Test application policy helpers without starting a graphical session."""

from importlib import metadata
from types import MethodType, SimpleNamespace
import os
import tempfile
import threading
import unittest
from unittest import mock

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from bwverify.bwverify import BwVerifyApplication, application_version
from bwverify.checksums import (
    ChecksumEntry,
    ChecksumFileError,
    calculate_checksum,
    parse_checksum_file,
    write_checksum_file,
)
from bwverify.document import new_document_format


# Lightweight stand-ins isolate controller policy from GTK's display-dependent widgets.
class FakeAction:
    """Record whether a controller action is available to the user."""

    def __init__(self):
        self.enabled = None

    def set_enabled(self, enabled):
        """Store the last requested enabled state."""
        self.enabled = enabled


class FakeStore:
    """Provide the small Gio.ListStore surface used by controller tests."""

    def __init__(self, items=()):
        self.items = list(items)

    def append(self, item):
        """Append an item in the same order as Gio.ListStore."""
        self.items.append(item)

    def get_item(self, position):
        """Return an item or ``None`` when a result arrives after removal."""
        return self.items[position] if position < len(self.items) else None

    def get_n_items(self):
        """Return the number of records currently displayed."""
        return len(self.items)

    def remove_all(self):
        """Clear the current document records."""
        self.items.clear()


class FakeProgress:
    """Capture progress text and fractions without creating GTK widgets."""

    def __init__(self):
        self.fraction = None
        self.text = None

    def set_fraction(self, fraction):
        """Store the latest numeric progress."""
        self.fraction = fraction

    def set_text(self, text):
        """Store the latest visible progress text."""
        self.text = text


class FakeLabel:
    """Capture status-line messages without creating GTK widgets."""

    def __init__(self):
        self.text = None

    def set_label(self, text):
        """Store the latest status-line text."""
        self.text = text


def make_item(filename, checksum, algorithm="SHA-256", status="Unknown"):
    """Create a record with the GObject properties used by the controller."""
    return SimpleNamespace(
        props=SimpleNamespace(
            filename=filename,
            checksum=checksum,
            algorithm=algorithm,
            status=status,
            icon_name="bwverify-unknown",
            actual_checksum="",
            detail="",
            source_path="",
        )
    )


def make_controller(items=(), document_mode="open"):
    """Create a display-free object with the controller's required state."""
    actions = {
        name: FakeAction()
        for name in (
            "new_action",
            "open_action",
            "add_files_action",
            "add_directory_action",
            "save_action",
            "verify_action",
            "close_file_action",
            "cancel_action",
        )
    }
    controller = SimpleNamespace(
        **actions,
        store=FakeStore(items),
        progress=FakeProgress(),
        status_label=FakeLabel(),
        is_verifying=False,
        cancel_event=None,
        verification_id=1,
        modal_dialog_count=0,
        window=None,
        document_mode=document_mode,
        checksum_directory=None,
        checksum_path="checksums.sha256",
        manifest_comments=["; comment"],
        manifest_style="sfv",
        checksum_algorithm="SHA-256",
        new_document_suggested_filename="checksums.sha256",
        default_checksum_format="sfv",
        new_document_path_mode="relative",
        default_path_mode="relative",
        file_encoding="utf-8",
        line_ending="lf",
    )
    for name in (
        "on_add_files_response",
        "finish_adding",
        "finish_verification",
        "show_message",
        "update_add_progress",
        "update_action_states",
        "update_verification_result",
        "begin_modal_dialog",
        "end_modal_dialog",
        "update_main_menu_sensitivity",
        "promote_filename_only_paths",
        "update_new_document_display_filenames",
    ):
        setattr(controller, name, MethodType(getattr(BwVerifyApplication, name), controller))
    return controller


def run_idle_callback(callback, *arguments):
    """Execute GLib idle work immediately for deterministic worker tests."""
    return callback(*arguments)


# Policy tests cover decisions that should not need a GTK application instance.
class ApplicationPolicyTests(unittest.TestCase):
    """Exercise policy decisions that do not require creating a GTK window."""

    def test_file_dialog_exposes_the_multiple_file_open_api(self):
        """The GTK runtime provides the API used by the Add files action."""
        self.assertTrue(callable(Gtk.FileDialog.open_multiple))
        self.assertTrue(callable(Gtk.FileDialog.open_multiple_finish))

    def test_applies_dark_theme_with_gtk_settings(self):
        """The explicit dark preference is forwarded to GTK's theme setting."""
        gtk_settings = mock.Mock()
        application = SimpleNamespace(window=mock.Mock(), theme="dark")

        with mock.patch(
            "bwverify.bwverify.Gtk.Settings.get_for_display", return_value=gtk_settings
        ):
            BwVerifyApplication.apply_theme(application)

        gtk_settings.set_property.assert_called_once_with(
            "gtk-application-prefer-dark-theme", True
        )

    def test_system_theme_uses_gtk_desktop_color_scheme(self):
        """The System preference follows GTK's desktop dark-mode signal."""
        gtk_settings = mock.Mock()
        gtk_settings.get_property.return_value = Gtk.InterfaceColorScheme.DARK
        application = SimpleNamespace(window=mock.Mock(), theme="system")

        with mock.patch(
            "bwverify.bwverify.Gtk.Settings.get_for_display", return_value=gtk_settings
        ):
            BwVerifyApplication.apply_theme(application)

        gtk_settings.set_property.assert_called_once_with(
            "gtk-application-prefer-dark-theme", True
        )

    def test_system_theme_falls_back_to_the_configured_gtk_theme(self):
        """A dark GTK theme works when the desktop does not report a scheme."""
        gtk_settings = mock.Mock()
        gtk_settings.get_property.side_effect = lambda name: {
            "gtk-interface-color-scheme": Gtk.InterfaceColorScheme.UNSUPPORTED,
            "gtk-theme-name": "Example-dark",
        }[name]
        application = SimpleNamespace(window=mock.Mock(), theme="system")

        with mock.patch(
            "bwverify.bwverify.Gtk.Settings.get_for_display", return_value=gtk_settings
        ):
            BwVerifyApplication.apply_theme(application)

        gtk_settings.set_property.assert_called_once_with(
            "gtk-application-prefer-dark-theme", True
        )

    def test_uses_installed_distribution_version(self):
        """The About dialog version comes from installed package metadata."""
        with mock.patch("bwverify.bwverify.metadata.version", return_value="2.3.4"):
            self.assertEqual(application_version(), "2.3.4")

    def test_labels_an_uninstalled_source_checkout_as_development(self):
        """Direct source execution does not need a duplicate version constant."""
        with mock.patch(
            "bwverify.bwverify.metadata.version",
            side_effect=metadata.PackageNotFoundError,
        ):
            self.assertEqual(application_version(), "development")

    def test_theme_selector_updates_and_persists_the_preference(self):
        """Changing Preferences applies the selected GTK theme and saves it."""
        selector = mock.Mock()
        selector.get_selected.return_value = 2
        application = SimpleNamespace(
            theme="system",
            apply_theme=mock.Mock(),
            refresh_icons=mock.Mock(),
            save_settings=mock.Mock(),
        )

        BwVerifyApplication.on_theme_changed(application, selector, None)

        self.assertEqual(application.theme, "dark")
        application.apply_theme.assert_called_once_with()
        application.refresh_icons.assert_called_once_with()
        application.save_settings.assert_called_once_with()

    def test_icon_set_selector_updates_visible_icons_and_persists(self):
        """Changing the icon set immediately refreshes and saves the preference."""
        selector = mock.Mock()
        selector.get_selected.return_value = 1
        application = SimpleNamespace(
            icon_set="oxygen",
            refresh_icons=mock.Mock(),
            save_settings=mock.Mock(),
        )

        BwVerifyApplication.on_icon_set_changed(application, selector, None)

        self.assertEqual(application.icon_set, "symbolic")
        application.refresh_icons.assert_called_once_with()
        application.save_settings.assert_called_once_with()

    def test_icon_set_selector_accepts_tango(self):
        """The third icon-set choice selects the bundled Tango artwork."""
        selector = mock.Mock()
        selector.get_selected.return_value = 2
        application = SimpleNamespace(
            icon_set="oxygen",
            refresh_icons=mock.Mock(),
            save_settings=mock.Mock(),
        )

        BwVerifyApplication.on_icon_set_changed(application, selector, None)

        self.assertEqual(application.icon_set, "tango")

    def test_file_output_selectors_update_and_persist_preferences(self):
        """Encoding and line-ending choices are retained for subsequent saves."""
        encoding_selector = mock.Mock()
        encoding_selector.get_selected.return_value = 2
        line_ending_selector = mock.Mock()
        line_ending_selector.get_selected.return_value = 1
        application = SimpleNamespace(
            file_encoding="utf-8",
            line_ending="lf",
            save_settings=mock.Mock(),
        )

        BwVerifyApplication.on_file_encoding_changed(application, encoding_selector, None)
        BwVerifyApplication.on_line_ending_changed(application, line_ending_selector, None)

        self.assertEqual(application.file_encoding, "utf-16")
        self.assertEqual(application.line_ending, "crlf")
        self.assertEqual(application.save_settings.call_count, 2)

    def test_main_menu_dims_for_each_modal_dialog_until_the_last_one_closes(self):
        """The menu button matches the header while any modal surface is active."""
        menu_button = mock.Mock()
        application = SimpleNamespace(
            window=SimpleNamespace(_menu_button=menu_button), modal_dialog_count=0
        )
        application.update_main_menu_sensitivity = MethodType(
            BwVerifyApplication.update_main_menu_sensitivity, application
        )

        BwVerifyApplication.begin_modal_dialog(application)
        BwVerifyApplication.begin_modal_dialog(application)
        BwVerifyApplication.end_modal_dialog(application)

        self.assertEqual(application.modal_dialog_count, 1)
        menu_button.set_sensitive.assert_has_calls([mock.call(False)] * 3)

        BwVerifyApplication.end_modal_dialog(application)

        self.assertEqual(application.modal_dialog_count, 0)
        self.assertEqual(menu_button.set_sensitive.call_args, mock.call(True))

    def test_closing_a_custom_dialog_restores_the_main_menu(self):
        """Custom modal windows release the same menu lock as file dialogs."""
        menu_button = mock.Mock()
        application = SimpleNamespace(
            window=SimpleNamespace(_menu_button=menu_button), modal_dialog_count=1
        )
        application.update_main_menu_sensitivity = MethodType(
            BwVerifyApplication.update_main_menu_sensitivity, application
        )
        application.end_modal_dialog = MethodType(
            BwVerifyApplication.end_modal_dialog, application
        )

        handled = BwVerifyApplication.on_modal_window_close_requested(application, mock.Mock())

        self.assertEqual(application.modal_dialog_count, 0)
        menu_button.set_sensitive.assert_called_once_with(True)
        self.assertFalse(handled)

    def test_custom_dialogs_use_the_gtk4_close_request_signal(self):
        """Every custom modal window uses the close path that releases its menu lock."""
        dialog = mock.Mock()
        application = SimpleNamespace(
            begin_modal_dialog=mock.Mock(),
            on_modal_window_close_requested=mock.Mock(),
        )

        BwVerifyApplication.present_modal_window(application, dialog)

        application.begin_modal_dialog.assert_called_once_with()
        dialog.connect.assert_called_once_with(
            "close-request", application.on_modal_window_close_requested
        )
        dialog.present.assert_called_once_with()

    def test_creating_a_document_requests_the_custom_dialog_to_close(self):
        """Creating a document follows the close-request path that restores the menu."""
        dialog = mock.Mock()
        format_selector = mock.Mock()
        path_selector = mock.Mock()
        format_selector.get_selected.return_value = 0
        path_selector.get_selected.return_value = 0
        application = SimpleNamespace(create_new_document=mock.Mock())

        BwVerifyApplication.on_new_document_create(
            application, mock.Mock(), dialog, format_selector, path_selector
        )

        application.create_new_document.assert_called_once_with("sfv", "relative")
        dialog.close.assert_called_once_with()


# Controller tests drive worker completions synchronously through the fake GTK surface.
class ApplicationControllerTests(unittest.TestCase):
    """Exercise verification and document state transitions without a display."""

    def test_action_states_follow_document_mode_and_worker_state(self):
        """Only actions applicable to the active document remain available."""
        controller = make_controller([make_item("file.txt", "ABC")], document_mode="open")
        controller.checksum_directory = "/checksums"

        BwVerifyApplication.update_action_states(controller)

        self.assertTrue(controller.new_action.enabled)
        self.assertTrue(controller.add_files_action.enabled)
        self.assertTrue(controller.save_action.enabled)
        self.assertTrue(controller.verify_action.enabled)
        self.assertTrue(controller.close_file_action.enabled)
        self.assertFalse(controller.cancel_action.enabled)

        controller.is_verifying = True
        BwVerifyApplication.update_action_states(controller)
        self.assertFalse(controller.new_action.enabled)
        self.assertFalse(controller.save_action.enabled)
        self.assertTrue(controller.cancel_action.enabled)

    def test_add_files_is_available_only_for_an_active_document(self):
        """Adding files requires a new or opened checksum document."""
        controller = make_controller([], document_mode=None)
        controller.window = object()

        BwVerifyApplication.update_action_states(controller)
        self.assertFalse(controller.add_files_action.enabled)
        self.assertFalse(controller.add_directory_action.enabled)

        controller.document_mode = "new"
        with mock.patch("bwverify.bwverify.Gtk.FileDialog") as file_dialog:
            BwVerifyApplication.update_action_states(controller)
            BwVerifyApplication.on_add_files(controller, None, None)

        self.assertTrue(controller.add_files_action.enabled)
        file_dialog.assert_called_once_with(title="Choose files to add")
        file_dialog.return_value.open_multiple.assert_called_once_with(
            controller.window, None, controller.on_add_files_response
        )

        controller.document_mode = "open"
        BwVerifyApplication.update_action_states(controller)
        self.assertTrue(controller.add_files_action.enabled)

    def test_adding_to_an_opened_document_uses_relative_manifest_paths(self):
        """New records display and save paths relative to the checksum file."""
        controller = make_controller([], document_mode="open")
        controller.checksum_directory = "/checksums"

        with mock.patch("bwverify.bwverify.FileItem", side_effect=make_item):
            BwVerifyApplication.finish_adding(
                controller,
                controller.verification_id,
                [("/checksums/files/added.txt", "A" * 64)],
                False,
            )

        item = controller.store.get_item(0)
        self.assertEqual(item.props.filename, "files/added.txt")
        self.assertEqual(item.props.source_path, "/checksums/files/added.txt")

    def test_adding_to_a_new_document_starts_verification(self):
        """New entries are immediately verified from their retained source paths."""
        controller = make_controller([], document_mode="new")
        controller.on_verify = mock.Mock()

        with mock.patch("bwverify.bwverify.FileItem", side_effect=make_item):
            BwVerifyApplication.finish_adding(
                controller,
                controller.verification_id,
                [("/files/added.txt", "A" * 64)],
                False,
            )

        self.assertEqual(controller.store.get_item(0).props.source_path, "/files/added.txt")
        controller.on_verify.assert_called_once_with(None, None)

    def test_filename_only_document_hides_source_paths_in_the_table(self):
        """Filename-only documents keep the table free of source directory names."""
        controller = make_controller([], document_mode="new")
        controller.new_document_path_mode = "filename"
        controller.on_verify = mock.Mock()

        with mock.patch("bwverify.bwverify.FileItem", side_effect=make_item):
            BwVerifyApplication.finish_adding(
                controller,
                controller.verification_id,
                [("/documents/source/file.txt", "A" * 64)],
                False,
            )

        self.assertEqual(controller.store.get_item(0).props.filename, "file.txt")
        self.assertEqual(controller.new_document_path_mode, "filename")

    def test_mixed_source_directories_promote_filename_only_document_to_relative(self):
        """Mixed folders use visible relative paths instead of ambiguous bare filenames."""
        controller = make_controller([make_item("one.txt", "A" * 64)], document_mode="new")
        controller.new_document_path_mode = "filename"
        controller.store.get_item(0).props.source_path = "/documents/first/one.txt"
        controller.on_verify = mock.Mock()

        with mock.patch("bwverify.bwverify.FileItem", side_effect=make_item):
            BwVerifyApplication.finish_adding(
                controller,
                controller.verification_id,
                [("/documents/second/two.txt", "B" * 64)],
                False,
            )

        self.assertEqual(controller.new_document_path_mode, "relative")
        self.assertEqual(controller.store.get_item(0).props.filename, "first/one.txt")
        self.assertEqual(controller.store.get_item(1).props.filename, "second/two.txt")
        self.assertIn("Switched to relative paths", controller.status_label.text)

    def test_on_verify_marks_records_and_starts_a_worker(self):
        """Starting verification creates checking records and a cancellable worker."""
        item = make_item("file.txt", "A" * 64)
        controller = make_controller([item])
        controller.checksum_directory = "/checksums"
        controller.verify_files = mock.Mock()
        worker = mock.Mock()

        with mock.patch("bwverify.bwverify.threading.Thread", return_value=worker) as thread:
            BwVerifyApplication.on_verify(controller, None, None)

        self.assertTrue(controller.is_verifying)
        self.assertIsInstance(controller.cancel_event, threading.Event)
        self.assertEqual(item.props.status, "Checking")
        self.assertEqual(item.props.detail, "Checking checksum…")
        self.assertEqual(controller.progress.text, "Checking 0/1")
        self.assertEqual(controller.status_label.text, "Verifying 1 file(s)…")
        self.assertFalse(controller.verify_action.enabled)
        self.assertTrue(controller.cancel_action.enabled)
        thread.assert_called_once()
        worker.start.assert_called_once_with()

    def test_new_document_verification_uses_the_original_source_path(self):
        """Unsaved documents do not require a manifest directory for verification."""
        item = make_item("file.txt", "A" * 64)
        item.props.source_path = "/files/file.txt"
        controller = make_controller([item], document_mode="new")
        controller.verify_files = mock.Mock()
        worker = mock.Mock()

        with mock.patch("bwverify.bwverify.threading.Thread", return_value=worker) as thread:
            BwVerifyApplication.on_verify(controller, None, None)

        records, base_directory, _cancel_event, _verification_id = thread.call_args.kwargs["args"]
        self.assertEqual(records[0][1], "/files/file.txt")
        self.assertIsNone(base_directory)
        worker.start.assert_called_once_with()

    def test_verification_reports_verified_mismatched_and_missing_files(self):
        """One worker run updates each result and gives an accurate completion summary."""
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "verified.txt")
            with open(source, "wb") as handle:
                handle.write(b"verified")
            expected = calculate_checksum(source, "SHA-256")
            records = [
                (0, "verified.txt", expected, "SHA-256"),
                (1, "verified.txt", "0" * 64, "SHA-256"),
                (2, "missing.txt", expected, "SHA-256"),
            ]
            controller = make_controller(
                [make_item(filename, checksum) for _, filename, checksum, _ in records]
            )
            controller.is_verifying = True

            with mock.patch("bwverify.bwverify.GLib.idle_add", side_effect=run_idle_callback):
                BwVerifyApplication.verify_files(
                    controller, records, directory, threading.Event(), controller.verification_id
                )

        self.assertEqual([item.props.status for item in controller.store.items],
                         ["Verified", "Mismatch", "Missing"])
        self.assertEqual(controller.progress.fraction, 1)
        self.assertEqual(controller.progress.text, "Verification complete")
        self.assertEqual(
            controller.status_label.text,
            "Verification complete: 1 verified, 1 mismatched, 1 missing, 0 unreadable.",
        )

    def test_verification_reports_errors_and_cancellation(self):
        """Unreadable records and pending records receive distinct terminal statuses."""
        error_controller = make_controller([make_item("unreadable.txt", "A" * 64)])
        error_controller.is_verifying = True
        error_records = [(0, "unreadable.txt", "A" * 64, "SHA-256")]
        with mock.patch(
            "bwverify.bwverify.calculate_checksum", side_effect=PermissionError("denied")
        ):
            with mock.patch("bwverify.bwverify.GLib.idle_add", side_effect=run_idle_callback):
                BwVerifyApplication.verify_files(
                    error_controller,
                    error_records,
                    "/checksums",
                    threading.Event(),
                    error_controller.verification_id,
                )
        self.assertEqual(error_controller.store.get_item(0).props.status, "Error")
        self.assertIn("1 unreadable", error_controller.status_label.text)

        cancelled_item = make_item("later.txt", "A" * 64, status="Checking")
        cancelled_controller = make_controller([cancelled_item])
        cancelled_controller.is_verifying = True
        cancel_event = threading.Event()
        cancel_event.set()
        with mock.patch("bwverify.bwverify.GLib.idle_add", side_effect=run_idle_callback):
            BwVerifyApplication.verify_files(
                cancelled_controller,
                [(0, "later.txt", "A" * 64, "SHA-256")],
                "/checksums",
                cancel_event,
                cancelled_controller.verification_id,
            )
        self.assertEqual(cancelled_item.props.status, "Cancelled")
        self.assertEqual(cancelled_controller.progress.text, "Verification cancelled")

    def test_cancel_and_close_reset_the_active_document(self):
        """Cancellation disables itself and closing clears all document-specific state."""
        controller = make_controller([make_item("file.txt", "A" * 64)])
        controller.cancel_event = threading.Event()

        BwVerifyApplication.on_cancel(controller, None, None)
        self.assertTrue(controller.cancel_event.is_set())
        self.assertFalse(controller.cancel_action.enabled)
        self.assertEqual(controller.status_label.text, "Cancelling after the current file…")

        BwVerifyApplication.on_close_file(controller, None, None)
        self.assertEqual(controller.store.get_n_items(), 0)
        self.assertIsNone(controller.document_mode)
        self.assertIsNone(controller.checksum_path)
        self.assertEqual(controller.manifest_comments, [])
        self.assertEqual(controller.progress.text, "Open a checksum file to begin.")

    def test_load_checksum_file_populates_a_document_and_reports_read_errors(self):
        """Loading converts manifest records to display items and leaves errors non-destructive."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = os.path.join(directory, "checksums.sha256")
            entry = ChecksumEntry("file.txt", "A" * 64, "SHA-256")
            write_checksum_file(manifest, [entry], comments=["; source comment"])
            controller = make_controller([], document_mode=None)
            controller.auto_verify_after_open = False

            with mock.patch("bwverify.bwverify.FileItem", side_effect=make_item):
                BwVerifyApplication.load_checksum_file(controller, manifest)

            self.assertEqual(controller.document_mode, "open")
            self.assertEqual(controller.checksum_path, manifest)
            self.assertEqual(controller.manifest_comments, ["; source comment"])
            self.assertEqual(controller.store.get_item(0).props.filename, "file.txt")
            self.assertEqual(controller.progress.text, "1 file(s) loaded")

            with mock.patch(
                "bwverify.bwverify.load_document",
                side_effect=ChecksumFileError("unable to read manifest"),
            ):
                BwVerifyApplication.load_checksum_file(controller, manifest)

        self.assertEqual(controller.status_label.text, "unable to read manifest")
        self.assertEqual(controller.store.get_n_items(), 1)

    def test_new_document_addition_and_save_use_relative_paths(self):
        """Creating a manifest calculates entries and saves them relative to its location."""
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "file.txt")
            manifest = os.path.join(directory, "checksums.sha256")
            with open(source, "wb") as handle:
                handle.write(b"contents")
            controller = make_controller([], document_mode=None)
            controller.on_verify = mock.Mock()

            BwVerifyApplication.create_new_document(controller, "sfv", "filename")
            self.assertEqual(controller.document_mode, "new")
            self.assertEqual(controller.manifest_style, "sfv")
            self.assertEqual(controller.checksum_algorithm, "CRC-32")
            self.assertEqual(controller.new_document_path_mode, "filename")

            with mock.patch("bwverify.bwverify.FileItem", side_effect=make_item):
                with mock.patch("bwverify.bwverify.GLib.idle_add", side_effect=run_idle_callback):
                    BwVerifyApplication.calculate_entries(
                        controller,
                        [source],
                        threading.Event(),
                        controller.verification_id,
                    )

            item = controller.store.get_item(0)
            self.assertEqual(item.props.source_path, source)
            self.assertEqual(item.props.algorithm, "CRC-32")
            controller.on_verify.assert_called_once_with(None, None)
            dialog = SimpleNamespace(
                save_finish=mock.Mock(
                    return_value=SimpleNamespace(get_path=mock.Mock(return_value=manifest))
                )
            )
            controller.file_dialog = dialog

            BwVerifyApplication.on_save_response(controller, dialog, object())

            self.assertEqual(parse_checksum_file(manifest)[0].filename, "file.txt")
            self.assertEqual(parse_checksum_file(manifest)[0].algorithm, "CRC-32")
            self.assertEqual(controller.progress.text, "Checksum file saved")

    def test_new_document_format_selects_algorithm_style_and_filename(self):
        """Each preset supplies coherent checksum calculation and save settings."""
        controller = make_controller([], document_mode=None)

        BwVerifyApplication.create_new_document(controller, "bsd-sha256", "absolute")

        self.assertEqual(controller.manifest_style, "bsd")
        self.assertEqual(controller.checksum_algorithm, "SHA-256")
        self.assertEqual(controller.new_document_suggested_filename, "checksums.sha256")
        self.assertEqual(controller.new_document_path_mode, "absolute")
        self.assertEqual(new_document_format("unknown").identifier, "sfv")

    def test_saving_an_open_document_preserves_its_selected_style_and_comments(self):
        """Saving an opened manifest retains its format unless the preference removes comments."""
        with tempfile.TemporaryDirectory() as directory:
            manifest = os.path.join(directory, "checks.sfv")
            controller = make_controller(
                [make_item("file.bin", "CBF43926", "CRC-32")], document_mode="open"
            )
            controller.checksum_path = manifest
            controller.manifest_style = "sfv"
            controller.manifest_comments = ["; retained comment"]
            controller.remove_comments_on_save = False
            controller.file_encoding = "utf-8-sig"
            controller.line_ending = "crlf"

            BwVerifyApplication.save_open_checksum_file(controller)

            with open(manifest, "rb") as handle:
                contents = handle.read()
        self.assertEqual(
            contents,
            b"\xef\xbb\xbf; retained comment\r\nfile.bin CBF43926\r\n",
        )

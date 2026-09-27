#!/usr/bin/env python3

"""A desktop application for verifying file integrity using checksum files."""

import os
import sys
import threading
from importlib import metadata

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from bwverify.checksums import (
    ChecksumFileError,
    ChecksumEntry,
    VerificationCancelled,
    calculate_checksum,
)
from bwverify.document import (
    FILE_ENCODINGS,
    LINE_ENDINGS,
    NEW_DOCUMENT_FORMATS,
    NEW_DOCUMENT_PATH_MODES,
    load_document,
    new_document_format,
    new_document_path_mode,
    save_new_document,
    save_open_document,
)
from bwverify.models import (
    ERROR_ICON_NAME,
    ICON_DIRECTORY,
    UNKNOWN_ICON_NAME,
    VERIFIED_ICON_NAME,
    WARNING_ICON_NAME,
    FileItem,
)
from bwverify.settings import ApplicationSettings, load_settings, save_settings
from bwverify.window import (
    create_saved_file_preferences_section,
    create_window,
    refresh_window_icons,
)


APPLICATION_ID = "org.bulkware.bwverify"
APPLICATION_NAME = "bwVerify"


def application_version():
    """Return installed package metadata, or a clear source-checkout label."""
    try:
        return metadata.version("bwVerify")
    except metadata.PackageNotFoundError:
        return "development"


class BwVerifyApplication(Gtk.Application):
    """GTK application for loading and verifying checksum files."""

    def __init__(self):
        super().__init__(
            application_id=APPLICATION_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self.connect("activate", self.on_activate)

        # Window and document state are retained for the lifetime of the application.
        self.window = None
        self.file_dialog = None
        self.modal_dialog_count = 0
        self.checksum_directory = None
        self.checksum_path = None
        self.manifest_comments = []
        self.manifest_style = "sfv"
        self.checksum_algorithm = "CRC-32"
        self.new_document_suggested_filename = "checksums.sfv"
        self.new_document_path_mode = "relative"
        self.document_mode = None
        self.is_verifying = False
        self.cancel_event = None
        self.verification_id = 0
        self.settings_path = os.path.join(
            GLib.get_user_config_dir(), APPLICATION_ID, "settings.conf"
        )
        self.legacy_settings_path = os.path.join(
            GLib.get_user_config_dir(), APPLICATION_ID, "settings.ini"
        )
        self.window_width = 800
        self.window_height = 600
        self.last_directory = None
        self.auto_verify_after_open = False
        self.remove_comments_on_save = False
        self.default_checksum_format = "sfv"
        self.default_path_mode = "relative"
        self.theme = "system"
        self.icon_set = "oxygen"
        self.file_encoding = "utf-8"
        self.line_ending = "lf"
        self.prefers_dark = False
        self.load_settings()

        # Actions are shared by header buttons, menu items, and keyboard shortcuts.
        self.open_action = Gio.SimpleAction.new("open", None)
        self.open_action.connect("activate", self.on_open)
        self.add_action(self.open_action)

        self.verify_action = Gio.SimpleAction.new("verify", None)
        self.verify_action.connect("activate", self.on_verify)
        self.verify_action.set_enabled(False)
        self.add_action(self.verify_action)

        self.cancel_action = Gio.SimpleAction.new("cancel", None)
        self.cancel_action.connect("activate", self.on_cancel)
        self.cancel_action.set_enabled(False)
        self.add_action(self.cancel_action)

        self.new_action = Gio.SimpleAction.new("new", None)
        self.new_action.connect("activate", self.on_new)
        self.add_action(self.new_action)

        self.add_files_action = Gio.SimpleAction.new("add-files", None)
        self.add_files_action.connect("activate", self.on_add_files)
        self.add_action(self.add_files_action)

        self.add_directory_action = Gio.SimpleAction.new("add-directory", None)
        self.add_directory_action.connect("activate", self.on_add_directory)
        self.add_action(self.add_directory_action)

        self.save_action = Gio.SimpleAction.new("save", None)
        self.save_action.connect("activate", self.on_save)
        self.add_action(self.save_action)

        self.close_file_action = Gio.SimpleAction.new("close-file", None)
        self.close_file_action.connect("activate", self.on_close_file)
        self.close_file_action.set_enabled(False)
        self.add_action(self.close_file_action)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self.on_about)
        self.add_action(about_action)

        preferences_action = Gio.SimpleAction.new("preferences", None)
        preferences_action.connect("activate", self.on_preferences)
        self.add_action(preferences_action)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self.on_quit)
        self.add_action(quit_action)
        # Keep quitting accessible from the keyboard without a primary-menu item.
        self.set_accels_for_action("app.quit", ["<Primary>q"])

        self.update_action_states()

    def on_activate(self, _application):
        """Create and present the primary window when the app activates."""
        if self.window is None:
            self.window = self.create_window()
            self.apply_theme()
            self.refresh_icons()
        self.window.present()

    def apply_theme(self):
        """Request the selected system, light, or dark variant from the GTK theme."""
        gtk_settings = Gtk.Settings.get_for_display(self.window.get_display())
        prefers_dark = self.theme == "dark" or (
            self.theme == "system" and BwVerifyApplication.system_prefers_dark(gtk_settings)
        )
        self.prefers_dark = prefers_dark
        gtk_settings.set_property("gtk-application-prefer-dark-theme", prefers_dark)

    @staticmethod
    def system_prefers_dark(gtk_settings):
        """Return GTK's desktop preference, falling back to a dark GTK theme name."""
        try:
            color_scheme = gtk_settings.get_property("gtk-interface-color-scheme")
            if color_scheme == Gtk.InterfaceColorScheme.DARK:
                return True
            if color_scheme == Gtk.InterfaceColorScheme.LIGHT:
                return False
        except (AttributeError, TypeError):
            pass
        theme_name = gtk_settings.get_property("gtk-theme-name") or ""
        return "dark" in theme_name.lower()

    def do_open(self, files, _n_files, _hint):
        """Open a checksum file supplied as a command-line argument."""
        self.activate()
        # The single-window controller intentionally opens only the first supplied file.
        if not files:
            return
        path = files[0].get_path()
        if path is None:
            self.show_message("Only local checksum files can be opened.")
            return
        self.load_checksum_file(path)

    def create_window(self):
        """Create and bind the primary application window."""
        return create_window(self, APPLICATION_NAME)

    def on_open(self, _action, _parameter):
        """Show the checksum-file chooser for the Open action."""
        if self.is_verifying:
            return
        self.file_dialog = Gtk.FileDialog(title="Choose a checksum file")
        if self.last_directory and os.path.isdir(self.last_directory):
            self.file_dialog.set_initial_folder(
                Gio.File.new_for_path(self.last_directory)
            )
        filters = Gio.ListStore.new(Gtk.FileFilter)
        checksum_filter = Gtk.FileFilter()
        checksum_filter.set_name("Checksum files")
        for pattern in (
            "*.sfv", "*.md5", "*.sha1", "*.sha224", "*.sha256", "*.sha384", "*.sha512"
        ):
            checksum_filter.add_pattern(pattern)
        filters.append(checksum_filter)
        all_files_filter = Gtk.FileFilter()
        all_files_filter.set_name("All files")
        all_files_filter.add_pattern("*")
        filters.append(all_files_filter)
        self.file_dialog.set_filters(filters)
        self.begin_modal_dialog()
        self.file_dialog.open(self.window, None, self.on_open_response)

    def on_new(self, _action, _parameter):
        """Offer a format choice before creating a new checksum manifest."""
        if self.is_verifying:
            return
        dialog = Gtk.Window(title="New checksum file", transient_for=self.window, modal=True)
        # The compact creation form only needs a title-bar close control.
        header_bar = Gtk.HeaderBar()
        header_bar.set_decoration_layout(":close")
        dialog.set_titlebar(header_bar)
        dialog.set_resizable(False)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(18)
        content.set_margin_end(18)
        content.set_margin_top(18)
        content.set_margin_bottom(18)

        # These rows keep the persistent format and filename choices visible together.
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        label = Gtk.Label(label="Checksum format:", hexpand=True, xalign=0)
        format_selector = self.create_format_selector(self.default_checksum_format)
        row.append(label)
        row.append(format_selector)
        content.append(row)

        path_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        path_label = Gtk.Label(label="Stored filenames:", hexpand=True, xalign=0)
        path_selector = self.create_path_selector(self.default_path_mode)
        path_row.append(path_label)
        path_row.append(path_selector)
        content.append(path_row)

        # Keep document creation and cancellation visible at the end of the form.
        action_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            halign=Gtk.Align.END,
        )
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", lambda _button: dialog.close())
        create_button = Gtk.Button(label="Create")
        create_button.connect(
            "clicked", self.on_new_document_create, dialog, format_selector, path_selector
        )
        dialog.set_default_widget(create_button)
        action_box.append(cancel_button)
        action_box.append(create_button)
        content.append(action_box)
        dialog.set_child(content)
        self.present_modal_window(dialog)

    @staticmethod
    def create_format_selector(selected_identifier):
        """Return a dropdown populated with supported new-document presets."""
        selector = Gtk.DropDown.new_from_strings(
            [document_format.label for document_format in NEW_DOCUMENT_FORMATS]
        )
        selected_format = new_document_format(selected_identifier)
        selected_index = NEW_DOCUMENT_FORMATS.index(selected_format)
        selector.set_selected(selected_index)
        return selector

    @staticmethod
    def create_path_selector(selected_identifier):
        """Return a dropdown populated with supported filename storage modes."""
        selector = Gtk.DropDown.new_from_strings(
            [path_mode.label for path_mode in NEW_DOCUMENT_PATH_MODES]
        )
        selected_path_mode = new_document_path_mode(selected_identifier)
        selected_index = NEW_DOCUMENT_PATH_MODES.index(selected_path_mode)
        selector.set_selected(selected_index)
        return selector

    def on_new_document_create(self, _button, dialog, format_selector, path_selector):
        """Create a document with the format and path mode selected in the window."""
        selected_format = NEW_DOCUMENT_FORMATS[format_selector.get_selected()]
        selected_path_mode = NEW_DOCUMENT_PATH_MODES[path_selector.get_selected()]
        self.create_new_document(selected_format.identifier, selected_path_mode.identifier)
        dialog.close()

    def create_new_document(self, format_identifier, path_mode_identifier=None):
        """Reset the application to create a document using the selected preset."""
        document_format = new_document_format(format_identifier)
        path_mode = new_document_path_mode(path_mode_identifier or self.default_path_mode)
        self.store.remove_all()
        self.document_mode = "new"
        self.checksum_directory = None
        self.checksum_path = None
        self.manifest_comments = []
        self.manifest_style = document_format.style
        self.checksum_algorithm = document_format.algorithm
        self.new_document_suggested_filename = document_format.suggested_filename
        self.new_document_path_mode = path_mode.identifier
        self.progress.set_fraction(0)
        self.progress.set_text(f"New {document_format.label} checksum file")
        self.show_message(
            f"New {document_format.label} checksum file. Add files or a directory to begin."
        )
        self.update_action_states()

    def on_add_files(self, _action, _parameter):
        """Show a file chooser for adding files to the active manifest."""
        if self.document_mode is None or self.is_verifying:
            return
        self.file_dialog = Gtk.FileDialog(title="Choose files to add")
        self.begin_modal_dialog()
        self.file_dialog.open_multiple(self.window, None, self.on_add_files_response)

    def on_add_files_response(self, dialog, result):
        """Start adding the local files selected in the file chooser."""
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return
        finally:
            self.file_dialog = None
            self.end_modal_dialog()
        paths = [files.get_item(index).get_path() for index in range(files.get_n_items())]
        paths = [path for path in paths if path is not None]
        if not paths:
            self.show_message("Only local files can be added.")
            return
        self.add_paths(paths)

    def on_add_directory(self, _action, _parameter):
        """Show a directory chooser for adding files to the active manifest."""
        if self.document_mode is None or self.is_verifying:
            return
        self.file_dialog = Gtk.FileDialog(title="Choose a directory to add")
        self.begin_modal_dialog()
        self.file_dialog.select_folder(
            self.window, None, self.on_add_directory_response
        )

    def on_add_directory_response(self, dialog, result):
        """Find and add the files in the directory chosen by the user."""
        try:
            directory = dialog.select_folder_finish(result).get_path()
        except GLib.Error:
            return
        finally:
            self.file_dialog = None
            self.end_modal_dialog()
        if directory is None:
            self.show_message("Only local directories can be checksummed.")
            return
        paths = []
        for root, _directories, filenames in os.walk(directory):
            paths.extend(os.path.join(root, filename) for filename in filenames)
        if not paths:
            self.show_message("The selected directory contains no files.")
            return
        self.add_paths(sorted(paths))

    def add_paths(self, paths):
        """Calculate checksums for paths in a worker thread."""
        # Use an operation identifier so a late worker callback cannot alter newer state.
        self.is_verifying = True
        self.verification_id += 1
        operation_id = self.verification_id
        self.cancel_event = threading.Event()
        self.progress.set_fraction(0)
        self.progress.set_text(f"Adding 0/{len(paths)}")
        self.show_message(f"Calculating {self.checksum_algorithm} checksums…")
        self.update_action_states()
        threading.Thread(
            target=self.calculate_entries,
            args=(paths, self.cancel_event, operation_id, self.checksum_algorithm),
            daemon=True,
        ).start()

    def calculate_entries(self, paths, cancel_event, operation_id, algorithm=None):
        """Calculate selected-file checksums outside GTK's main thread."""
        algorithm = algorithm or self.checksum_algorithm
        entries = []
        try:
            for position, path in enumerate(paths, start=1):
                checksum = calculate_checksum(path, algorithm, cancel_event.is_set)
                entries.append((path, checksum))
                # GTK widgets are updated only after control returns to the main loop.
                GLib.idle_add(self.update_add_progress, operation_id, position, len(paths))
        except VerificationCancelled:
            GLib.idle_add(self.finish_adding, operation_id, None, True)
            return
        except OSError as error:
            GLib.idle_add(self.finish_adding, operation_id, str(error), False)
            return
        GLib.idle_add(self.finish_adding, operation_id, entries, False)

    def update_add_progress(self, operation_id, completed, total):
        """Update progress for the active checksum-creation operation."""
        if operation_id != self.verification_id:
            return False
        self.progress.set_fraction(completed / total)
        self.progress.set_text(f"Adding {completed}/{total}")
        return False

    def finish_adding(self, operation_id, result, cancelled):
        """Apply a completed checksum-creation result in GTK's main thread."""
        if operation_id != self.verification_id:
            return False
        self.is_verifying = False
        self.cancel_event = None
        if cancelled:
            self.progress.set_text("Adding files cancelled")
            self.show_message("Adding files was cancelled.")
        elif isinstance(result, list):
            switched_to_relative_paths = self.promote_filename_only_paths(result)
            for path, checksum in result:
                # Manifest records stay relative to the opened checksum file.
                filename = path
                if self.document_mode == "open" and self.checksum_directory:
                    filename = os.path.relpath(path, self.checksum_directory)
                item = FileItem(filename, checksum, self.checksum_algorithm)
                item.props.source_path = path
                self.store.append(item)
            if self.document_mode == "new":
                self.update_new_document_display_filenames()
            self.progress.set_fraction(1)
            self.progress.set_text(f"{len(result)} file(s) added")
            message = f"Added {len(result)} file(s)."
            if switched_to_relative_paths:
                message += " Switched to relative paths for files from different folders."
            self.show_message(message)
        else:
            self.progress.set_text("Adding files failed")
            self.show_message(f"Unable to add files: {result}")
        self.update_action_states()
        # New records retain their source paths, so they can be verified before saving.
        if isinstance(result, list) and result and self.document_mode == "new":
            self.on_verify(None, None)
        return False

    def promote_filename_only_paths(self, entries):
        """Use relative paths when filename-only entries span more than one directory."""
        if self.document_mode != "new" or self.new_document_path_mode != "filename":
            return False
        source_paths = [
            self.store.get_item(position).props.source_path
            for position in range(self.store.get_n_items())
        ]
        source_paths.extend(path for path, _checksum in entries)
        directories = {os.path.abspath(os.path.dirname(path)) for path in source_paths if path}
        if len(directories) < 2:
            return False
        self.new_document_path_mode = "relative"
        return True

    def update_new_document_display_filenames(self):
        """Show compact names, or relative paths when a new document needs them."""
        items = [self.store.get_item(position) for position in range(self.store.get_n_items())]
        source_paths = [item.props.source_path for item in items if item.props.source_path]
        if self.new_document_path_mode == "filename":
            for item in items:
                item.props.filename = os.path.basename(item.props.source_path)
            return
        if self.new_document_path_mode == "absolute":
            for item in items:
                item.props.filename = item.props.source_path
            return
        if not source_paths:
            return
        display_directory = BwVerifyApplication.common_source_directory(source_paths)
        for item in items:
            if display_directory is None:
                item.props.filename = item.props.source_path
            else:
                item.props.filename = os.path.relpath(item.props.source_path, display_directory)

    @staticmethod
    def common_source_directory(source_paths):
        """Return the common directory used to make source-path labels compact."""
        directories = [os.path.abspath(os.path.dirname(path)) for path in source_paths]
        try:
            return os.path.commonpath(directories)
        except ValueError:
            # Different Windows volumes do not have a representable common relative path.
            return None

    def on_save(self, _action, _parameter):
        """Save the current manifest, prompting for a new-file destination."""
        if self.store.get_n_items() == 0:
            return
        if self.document_mode == "open":
            self.save_open_checksum_file()
            return
        if self.document_mode != "new":
            return
        self.file_dialog = Gtk.FileDialog(title="Save checksum file")
        self.file_dialog.set_initial_name(self.new_document_suggested_filename)
        self.begin_modal_dialog()
        self.file_dialog.save(self.window, None, self.on_save_response)

    def on_save_response(self, dialog, result):
        """Write a new manifest to the destination selected in the save dialog."""
        try:
            file = dialog.save_finish(result)
        except GLib.Error:
            return
        finally:
            self.file_dialog = None
            self.end_modal_dialog()
        filepath = file.get_path()
        if filepath is None:
            self.show_message("Only local checksum files can be saved.")
            return
        # Source paths retain enough information for the chosen save-path policy.
        records = [
            (
                self.store.get_item(position).props.source_path,
                self.store.get_item(position).props.checksum,
                self.store.get_item(position).props.algorithm,
            )
            for position in range(self.store.get_n_items())
        ]
        try:
            entries = save_new_document(
                filepath,
                records,
                self.manifest_style,
                self.new_document_path_mode,
                self.file_encoding,
                self.line_ending,
            )
        except (ChecksumFileError, OSError) as error:
            self.show_message(f"Unable to save checksum file: {error}")
            return
        for position, entry in enumerate(entries):
            self.store.get_item(position).props.filename = entry.filename
        self.last_directory = os.path.dirname(filepath)
        self.progress.set_fraction(1)
        self.progress.set_text("Checksum file saved")
        self.show_message(f"Saved checksum file: {filepath}")

    def save_open_checksum_file(self):
        """Save edits to the checksum manifest currently open in the application."""
        if self.checksum_path is None:
            return
        entries = [
            ChecksumEntry(
                self.store.get_item(position).props.filename,
                self.store.get_item(position).props.checksum,
                self.store.get_item(position).props.algorithm,
            )
            for position in range(self.store.get_n_items())
        ]
        comments = () if self.remove_comments_on_save else self.manifest_comments
        try:
            save_open_document(
                self.checksum_path,
                entries,
                self.manifest_style,
                comments,
                self.file_encoding,
                self.line_ending,
            )
        except (ChecksumFileError, OSError) as error:
            self.show_message(f"Unable to save checksum file: {error}")
            return
        self.manifest_comments = list(comments)
        self.progress.set_fraction(1)
        self.progress.set_text("Checksum file saved")
        self.show_message(f"Saved checksum file: {self.checksum_path}")

    def on_open_response(self, dialog, result):
        """Load the local checksum file selected in the open dialog."""
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        finally:
            self.file_dialog = None
            self.end_modal_dialog()

        path = file.get_path()
        if path is None:
            self.show_message("Only local checksum files can be opened.")
            return
        self.load_checksum_file(path)

    def load_checksum_file(self, filepath):
        """Load a checksum manifest and populate the document records."""
        if self.is_verifying:
            return
        try:
            document = load_document(filepath)
        except ChecksumFileError as error:
            self.show_message(str(error))
            return

        # Opened manifests resolve relative entries against their own directory.
        self.store.remove_all()
        for entry in document.entries:
            item = FileItem(entry.filename, entry.checksum, entry.algorithm)
            item.props.source_path = os.path.join(os.path.dirname(filepath), entry.filename)
            self.store.append(item)

        self.checksum_directory = os.path.dirname(filepath)
        self.checksum_path = filepath
        self.manifest_comments = document.comments
        self.manifest_style = document.style
        self.checksum_algorithm = document.entries[0].algorithm
        self.document_mode = "open"
        self.last_directory = self.checksum_directory
        self.progress.set_fraction(0)
        self.progress.set_text(f"{len(document.entries)} file(s) loaded")
        self.show_message(
            f"Loaded {len(document.entries)} checksum record(s) from {os.path.basename(filepath)}."
        )
        self.update_action_states()
        if self.auto_verify_after_open:
            self.on_verify(None, None)

    def on_verify(self, _action, _parameter):
        """Begin verifying all records in the active checksum document."""
        if (
            self.is_verifying
            or self.document_mode not in ("new", "open")
            or self.store.get_n_items() == 0
        ):
            return

        # Snapshot row data before starting the worker so GTK state remains main-thread-only.
        records = []
        for position in range(self.store.get_n_items()):
            item = self.store.get_item(position)
            item.props.status = "Checking"
            item.props.icon_name = "process-working-symbolic"
            item.props.actual_checksum = ""
            item.props.detail = "Checking checksum…"
            filename = item.props.filename
            if self.document_mode == "new":
                filename = item.props.source_path
            records.append((position, filename, item.props.checksum, item.props.algorithm))

        self.is_verifying = True
        self.verification_id += 1
        verification_id = self.verification_id
        self.cancel_event = threading.Event()
        self.update_action_states()
        self.progress.set_fraction(0)
        self.progress.set_text(f"Checking 0/{len(records)}")
        self.show_message(f"Verifying {len(records)} file(s)…")

        worker = threading.Thread(
            target=self.verify_files,
            args=(
                records,
                self.checksum_directory if self.document_mode == "open" else None,
                self.cancel_event,
                verification_id,
            ),
            daemon=True,
        )
        worker.start()

    def on_cancel(self, _action, _parameter):
        """Request cancellation of the currently running checksum operation."""
        if self.cancel_event is not None:
            self.cancel_event.set()
            self.cancel_action.set_enabled(False)
            self.show_message("Cancelling after the current file…")

    def on_close_file(self, _action, _parameter):
        """Close the current manifest and reset document-specific state."""
        if self.is_verifying:
            return
        self.store.remove_all()
        self.checksum_directory = None
        self.checksum_path = None
        self.manifest_comments = []
        default_format = new_document_format(self.default_checksum_format)
        self.manifest_style = default_format.style
        self.checksum_algorithm = default_format.algorithm
        self.new_document_suggested_filename = default_format.suggested_filename
        self.new_document_path_mode = self.default_path_mode
        self.document_mode = None
        self.progress.set_fraction(0)
        self.progress.set_text("Open a checksum file to begin.")
        self.show_message("Checksum file closed.")
        self.update_action_states()

    def on_file_drop(self, _target, file_list, _x, _y):
        """Open the first local checksum file dropped on the application window."""
        if self.is_verifying:
            return False
        files = file_list.get_files()
        if not files:
            return False
        filepath = files[0].get_path()
        if filepath is None:
            self.show_message("Only local checksum files can be opened.")
            return False
        self.load_checksum_file(filepath)
        return True

    def verify_files(self, records, base_directory, cancel_event, verification_id):
        """Verify records outside GTK's main thread."""
        # Count every terminal state for a concise summary after the final callback.
        results = {"Verified": 0, "Mismatch": 0, "Missing": 0, "Error": 0}
        total = len(records)
        completed = 0
        cancelled = False

        for completed, (position, filename, expected, algorithm) in enumerate(
            records, start=1
        ):
            if cancel_event.is_set():
                cancelled = True
                completed -= 1
                break
            filepath = (
                filename
                if base_directory is None
                # ``os.path.join`` preserves absolute manifest entries unchanged.
                else os.path.join(base_directory, filename)
            )
            try:
                actual = calculate_checksum(filepath, algorithm, cancel_event.is_set)
            except VerificationCancelled:
                cancelled = True
                completed -= 1
                break
            except FileNotFoundError:
                status, icon_name, actual, detail = (
                    "Missing", WARNING_ICON_NAME, "", "File not found."
                )
            except OSError as error:
                status, icon_name, actual, detail = (
                    "Error", ERROR_ICON_NAME, "", str(error)
                )
            else:
                if actual == expected:
                    status, icon_name, detail = (
                        "Verified", VERIFIED_ICON_NAME, "Checksum matches."
                    )
                else:
                    status, icon_name, detail = (
                        "Mismatch", ERROR_ICON_NAME,
                        f"Expected {expected}, got {actual}.",
                    )

            results[status] += 1
            GLib.idle_add(
                self.update_verification_result,
                verification_id,
                position,
                status,
                icon_name,
                actual,
                detail,
                completed,
                total,
            )

        GLib.idle_add(
            self.finish_verification, verification_id, results, total, completed, cancelled
        )

    def update_verification_result(
        self, verification_id, position, status, icon_name, actual, detail, completed, total
    ):
        """Update one verification record and the overall progress display."""
        if verification_id != self.verification_id:
            return False
        item = self.store.get_item(position)
        if item is not None:
            item.props.status = status
            item.props.icon_name = icon_name
            item.props.actual_checksum = actual
            item.props.detail = detail
        self.progress.set_fraction(completed / total)
        self.progress.set_text(f"Checking {completed}/{total}")
        return False

    def finish_verification(self, verification_id, results, total, completed, cancelled):
        """Finish verification and summarize its completed or cancelled outcome."""
        if verification_id != self.verification_id:
            return False
        self.is_verifying = False
        self.cancel_event = None
        self.update_action_states()
        if cancelled:
            for position in range(self.store.get_n_items()):
                item = self.store.get_item(position)
                if item.props.status == "Checking":
                    item.props.status = "Cancelled"
                    item.props.icon_name = UNKNOWN_ICON_NAME
                    item.props.detail = "Verification was cancelled."
            self.progress.set_fraction(completed / total)
            self.progress.set_text("Verification cancelled")
            summary = f"Verification cancelled after {completed}/{total} file(s)."
        else:
            self.progress.set_fraction(1)
            self.progress.set_text("Verification complete")
            summary = (
                f"Verification complete: {results['Verified']} verified, "
                f"{results['Mismatch']} mismatched, {results['Missing']} missing, "
                f"{results['Error']} unreadable."
            )
        self.show_message(summary)
        return False

    def on_about(self, _action, _parameter):
        """Show the application information dialog."""
        dialog = Gtk.AboutDialog(transient_for=self.window, modal=True)
        logo_file = Gio.File.new_for_path(
            str(ICON_DIRECTORY.joinpath("org.bulkware.bwverify.svg"))
        )
        dialog.set_logo(Gdk.Texture.new_from_file(logo_file))
        dialog.set_program_name(APPLICATION_NAME)
        dialog.set_version(application_version())
        dialog.set_comments(
            "A desktop application for verifying file integrity using checksum files."
        )
        dialog.set_website("https://github.com/bulkware/bwverify")
        dialog.set_license_type(Gtk.License.GPL_3_0)
        self.present_modal_window(dialog)

    def begin_modal_dialog(self):
        """Dim the main-menu button while a modal surface owns the application."""
        self.modal_dialog_count += 1
        self.update_main_menu_sensitivity()

    def end_modal_dialog(self):
        """Restore the main-menu button after the last modal surface closes."""
        self.modal_dialog_count = max(0, self.modal_dialog_count - 1)
        self.update_main_menu_sensitivity()

    def update_main_menu_sensitivity(self):
        """Keep the independent menu button aligned with modal header-bar controls."""
        window = getattr(self, "window", None)
        menu_button = getattr(window, "_menu_button", None)
        if menu_button is not None:
            menu_button.set_sensitive(self.modal_dialog_count == 0)

    def present_modal_window(self, dialog):
        """Present a custom modal window and restore the parent menu when it closes."""
        self.begin_modal_dialog()
        dialog.connect("close-request", self.on_modal_window_close_requested)
        dialog.present()

    def on_modal_window_close_requested(self, _dialog):
        """Release the parent-menu lock before GTK closes a custom modal window."""
        self.end_modal_dialog()
        return False

    @staticmethod
    def create_preferences_section(title):
        """Return a vertically spaced Preferences section with a bold heading."""
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        heading = Gtk.Label(xalign=0)
        heading.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>")
        section.append(heading)
        return section

    def on_preferences(self, _action, _parameter):
        """Show controls for persisted verification and save preferences."""
        dialog = Gtk.Window(title="Preferences", transient_for=self.window, modal=True)
        # Preferences is a compact task window, so only expose its close control.
        header_bar = Gtk.HeaderBar()
        header_bar.set_decoration_layout(":close")
        dialog.set_titlebar(header_bar)
        dialog.set_resizable(False)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.set_margin_start(18)
        content.set_margin_end(18)
        content.set_margin_top(18)
        content.set_margin_bottom(18)

        # Appearance contains settings that take effect immediately in the main window.
        appearance_section = self.create_preferences_section("Appearance")
        theme_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        theme_label = Gtk.Label(label="Theme:", hexpand=True, xalign=0)
        theme_selector = Gtk.DropDown.new_from_strings(["System", "Light", "Dark"])
        theme_selector.set_selected(("system", "light", "dark").index(self.theme))
        theme_selector.connect("notify::selected", self.on_theme_changed)
        theme_row.append(theme_label)
        theme_row.append(theme_selector)
        appearance_section.append(theme_row)

        icon_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        icon_label = Gtk.Label(label="Icon set:", hexpand=True, xalign=0)
        icon_selector = Gtk.DropDown.new_from_strings(["Oxygen", "GTK Symbolic", "Tango"])
        icon_selector.set_selected(("oxygen", "symbolic", "tango").index(self.icon_set))
        icon_selector.connect("notify::selected", self.on_icon_set_changed)
        icon_row.append(icon_label)
        icon_row.append(icon_selector)
        appearance_section.append(icon_row)
        content.append(appearance_section)

        # New checksum files groups defaults used when a document is first created.
        new_document_section = self.create_preferences_section("New checksum files")
        format_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        format_label = Gtk.Label(label="Default checksum format:", hexpand=True, xalign=0)
        format_selector = self.create_format_selector(self.default_checksum_format)
        format_selector.connect("notify::selected", self.on_default_format_changed)
        format_row.append(format_label)
        format_row.append(format_selector)
        new_document_section.append(format_row)

        path_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        path_label = Gtk.Label(label="Stored filenames:", hexpand=True, xalign=0)
        path_selector = self.create_path_selector(self.default_path_mode)
        path_selector.connect("notify::selected", self.on_default_path_mode_changed)
        path_row.append(path_label)
        path_row.append(path_selector)
        new_document_section.append(path_row)
        content.append(new_document_section)

        content.append(create_saved_file_preferences_section(self, self.create_preferences_section))

        # Behaviour controls actions applied while working with existing manifests.
        behaviour_section = self.create_preferences_section("Behaviour")
        auto_verify = Gtk.CheckButton(label="Automatically verify files after opening")
        auto_verify.set_active(self.auto_verify_after_open)
        auto_verify.connect("toggled", self.on_auto_verify_toggled)
        behaviour_section.append(auto_verify)

        remove_comments = Gtk.CheckButton(
            label="Automatically remove comment lines on save"
        )
        remove_comments.set_active(self.remove_comments_on_save)
        remove_comments.connect("toggled", self.on_remove_comments_toggled)
        behaviour_section.append(remove_comments)
        content.append(behaviour_section)

        # A regular window owns its Close button instead of using dialog responses.
        close_button = Gtk.Button(label="Close", halign=Gtk.Align.END)
        close_button.connect("clicked", lambda _button: dialog.close())
        content.append(close_button)
        dialog.set_child(content)
        self.present_modal_window(dialog)

    def on_auto_verify_toggled(self, button):
        """Store the automatic-verification preference selected by the user."""
        self.auto_verify_after_open = button.get_active()
        self.save_settings()

    def on_remove_comments_toggled(self, button):
        """Store whether comments are removed while saving an open manifest."""
        self.remove_comments_on_save = button.get_active()
        self.save_settings()

    def on_theme_changed(self, selector, _property):
        """Apply and retain the light or dark theme selected in Preferences."""
        self.theme = ("system", "light", "dark")[selector.get_selected()]
        self.apply_theme()
        self.refresh_icons()
        self.save_settings()

    def on_icon_set_changed(self, selector, _property):
        """Apply and retain the selected bundled or GTK symbolic icon presentation."""
        self.icon_set = ("oxygen", "symbolic", "tango")[selector.get_selected()]
        self.refresh_icons()
        self.save_settings()

    def refresh_icons(self):
        """Update visible icons when the selected icon set changes."""
        if self.window is not None:
            refresh_window_icons(self.window, self)

    def on_default_format_changed(self, selector, _property):
        """Store the preset selected for future checksum documents."""
        selected_format = NEW_DOCUMENT_FORMATS[selector.get_selected()]
        self.default_checksum_format = selected_format.identifier
        self.save_settings()

    def on_default_path_mode_changed(self, selector, _property):
        """Store the path mode selected for future checksum documents."""
        selected_path_mode = NEW_DOCUMENT_PATH_MODES[selector.get_selected()]
        self.default_path_mode = selected_path_mode.identifier
        self.save_settings()

    def on_file_encoding_changed(self, selector, _property):
        """Store the output encoding used whenever a checksum document is saved."""
        self.file_encoding = FILE_ENCODINGS[selector.get_selected()].identifier
        self.save_settings()

    def on_line_ending_changed(self, selector, _property):
        """Store the output line ending used whenever a checksum document is saved."""
        self.line_ending = LINE_ENDINGS[selector.get_selected()].identifier
        self.save_settings()

    def on_selection_changed(self, selection, _position, _n_items):
        """Show details for the currently selected checksum record."""
        item = selection.get_selected_item()
        if item is None:
            self.show_message("Select a file to see its details.")
            return
        detail = item.props.detail or f"Expected checksum: {item.props.checksum}."
        self.show_message(f"{item.props.filename}: {detail}")

    def on_quit(self, _action, _parameter):
        """Quit the application when the corresponding action is activated."""
        self.quit()

    def update_action_states(self):
        """Keep document actions available only when they apply."""
        busy = self.is_verifying
        has_document = self.document_mode is not None
        has_records = self.store.get_n_items() > 0 if hasattr(self, "store") else False
        self.new_action.set_enabled(not busy)
        self.open_action.set_enabled(not busy)
        # Adding needs either a new or an opened checksum document.
        can_add = not busy and self.document_mode is not None
        self.add_files_action.set_enabled(can_add)
        self.add_directory_action.set_enabled(can_add)
        self.save_action.set_enabled(not busy and has_document and has_records)
        self.verify_action.set_enabled(
            not busy and self.document_mode in ("new", "open") and has_records
        )
        self.close_file_action.set_enabled(not busy and has_document)
        self.cancel_action.set_enabled(busy)

    def on_window_close(self, window):
        """Persist the window size when the primary window closes."""
        self.window_width = window.get_width()
        self.window_height = window.get_height()
        self.save_settings()
        return False

    def show_message(self, message):
        """Display a transient status message in the primary window."""
        self.status_label.set_label(message)

    def load_settings(self):
        """Load persistent settings into the GTK application state."""
        # Rebuild dependent document defaults after settings validation completes.
        values = load_settings(self.settings_path, self.legacy_settings_path)
        self.window_width = values.window_width
        self.window_height = values.window_height
        self.last_directory = values.last_directory
        self.auto_verify_after_open = values.auto_verify_after_open
        self.remove_comments_on_save = values.remove_comments_on_save
        self.default_checksum_format = values.default_checksum_format
        self.default_path_mode = values.default_path_mode
        self.theme = values.theme
        self.icon_set = values.icon_set
        self.file_encoding = values.file_encoding
        self.line_ending = values.line_ending
        default_format = new_document_format(self.default_checksum_format)
        self.manifest_style = default_format.style
        self.checksum_algorithm = default_format.algorithm
        self.new_document_suggested_filename = default_format.suggested_filename
        self.new_document_path_mode = self.default_path_mode

    def save_settings(self):
        """Persist settings currently held by the GTK application."""
        values = ApplicationSettings(
            window_width=self.window_width,
            window_height=self.window_height,
            last_directory=self.last_directory,
            auto_verify_after_open=self.auto_verify_after_open,
            remove_comments_on_save=self.remove_comments_on_save,
            default_checksum_format=self.default_checksum_format,
            default_path_mode=self.default_path_mode,
            theme=self.theme,
            icon_set=self.icon_set,
            file_encoding=self.file_encoding,
            line_ending=self.line_ending,
        )
        save_settings(self.settings_path, values)


def main():
    """Run the GTK application with the process command-line arguments."""
    return BwVerifyApplication().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())

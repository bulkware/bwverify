"""Construction helpers for the application's GTK window."""

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gio, GObject, Gtk, Pango

from bwverify.document import FILE_ENCODINGS, LINE_ENDINGS, file_encoding, line_ending
from bwverify.models import ICON_DIRECTORY, FileItem, header_icon, result_icon

# Keep result feedback visible even when a long filename takes most of the table width.
TABLE_COLUMNS = (
    ("Result", None),
    ("File", "filename"),
    ("Algorithm", "algorithm"),
    ("Checksum", "checksum"),
    ("Status", "status"),
)


def create_window(application, application_name):
    """Build the main window and attach its widgets to *application*."""
    window = Gtk.ApplicationWindow(application=application, title=application_name)
    # Retain image widgets so the preference can update the header immediately.
    window._icon_images = []
    configure_application_icon(window, application.get_application_id())
    window.set_default_size(application.window_width, application.window_height)
    window.connect("close-request", application.on_window_close)

    header_bar = Gtk.HeaderBar()
    # Keep system window controls without reserving a left-side application icon.
    header_bar.set_decoration_layout(":minimize,maximize,close")
    # Group related actions so the header bar stays scannable on wide desktops.
    action_groups = (
        (
            ("new", "New checksum file", "app.new"),
            ("open", "Open checksum file", "app.open"),
            ("close", "Close checksum file", "app.close-file"),
        ),
        (
            ("add-files", "Add files", "app.add-files"),
            ("add-directory", "Add a directory's files", "app.add-directory"),
            ("save", "Save checksum file", "app.save"),
        ),
        (
            ("verify", "Verify files", "app.verify"),
            ("cancel", "Cancel verification", "app.cancel"),
        ),
    )
    for index, actions in enumerate(action_groups):
        group = create_action_group(actions, application)
        header_bar.pack_start(group)
        window._icon_images.extend(group._icon_images)
        if index < len(action_groups) - 1:
            header_bar.pack_start(Gtk.Separator.new(Gtk.Orientation.VERTICAL))
    # Keep secondary actions in a primary menu beside the window controls.
    menu_button = Gtk.MenuButton()
    menu_image = create_icon_image(
        header_icon(application.icon_set, "menu", application.prefers_dark),
        16,
    )
    menu_button.set_child(menu_image)
    window._icon_images.append((menu_image, "menu", 16))
    menu_button.set_tooltip_text("Main menu")
    menu_button.set_menu_model(create_primary_menu())
    # Modal dialogs need to dim this independent button explicitly.
    window._menu_button = menu_button
    header_bar.pack_end(menu_button)
    window.set_titlebar(header_bar)

    # Accept file-manager drops without changing the source files themselves.
    drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
    drop_target.connect("drop", application.on_file_drop)
    window.add_controller(drop_target)

    application.store = Gio.ListStore.new(FileItem)
    # One selected row supplies the detail text in the status area.
    selection = Gtk.SingleSelection.new(application.store)
    selection.connect("selection-changed", application.on_selection_changed)
    column_view = create_column_view(selection, application)

    scrolled = Gtk.ScrolledWindow(child=column_view, hexpand=True, vexpand=True)
    application.progress = Gtk.ProgressBar(show_text=True)
    application.progress.set_text("Open a checksum file to begin.")
    application.status_label = create_status_label("Open a checksum file to begin.")

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.set_margin_start(12)
    box.set_margin_end(12)
    box.set_margin_top(6)
    box.set_margin_bottom(12)
    for widget in (scrolled, application.progress, application.status_label):
        box.append(widget)
    window.set_child(box)
    return window


def create_primary_menu():
    """Return the flat primary menu, grouped by task."""
    menu = Gio.Menu()
    # Sections add separators without requiring nested File and Help menus.
    action_groups = (
        (
            ("New checksum file", "app.new"),
            ("Open checksum file…", "app.open"),
            ("Close checksum file", "app.close-file"),
        ),
        (
            ("Add files…", "app.add-files"),
            ("Add directory…", "app.add-directory"),
            ("Save checksum file…", "app.save"),
        ),
        (
            ("Verify files", "app.verify"),
            ("Cancel verification", "app.cancel"),
        ),
        (
            ("Preferences", "app.preferences"),
            ("About bwVerify", "app.about"),
        ),
    )
    for actions in action_groups:
        section = Gio.Menu()
        for label, action in actions:
            section.append(label, action)
        menu.append_section(None, section)
    return menu


def configure_application_icon(window, application_id):
    """Make the packaged application icon available to GTK and the window manager."""
    icon_theme = Gtk.IconTheme.get_for_display(window.get_display())
    icon_theme.add_search_path(str(ICON_DIRECTORY))
    Gtk.Window.set_default_icon_name(application_id)
    window.set_icon_name(application_id)


def create_action_group(actions, application):
    """Return a visually linked header-bar group for related application actions."""
    group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    group.add_css_class("linked")
    group._icon_images = []
    for name, tooltip, action_name in actions:
        button, image = create_header_button(
            header_icon(application.icon_set, name, application.prefers_dark), tooltip, action_name
        )
        group.append(button)
        group._icon_images.append((image, name, 22))
    return group


def create_status_label(text):
    """Return a single-line status label that truncates long messages gracefully."""
    label = Gtk.Label(label=text, halign=Gtk.Align.START, hexpand=True)
    label.set_ellipsize(Pango.EllipsizeMode.END)
    label.set_single_line_mode(True)
    return label


def create_saved_file_preferences_section(application, create_section):
    """Build the saved-file preferences shared by new and opened manifests."""
    section = create_section("Saved checksum files")
    # Both preferences control the common writer, so they must remain adjacent in the UI.
    output_rows = (
        (
            "File encoding:",
            FILE_ENCODINGS,
            file_encoding(application.file_encoding),
            application.on_file_encoding_changed,
        ),
        (
            "Line endings:",
            LINE_ENDINGS,
            line_ending(application.line_ending),
            application.on_line_ending_changed,
        ),
    )
    for label_text, choices, selected_choice, callback in output_rows:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        label = Gtk.Label(label=label_text, hexpand=True, xalign=0)
        selector = Gtk.DropDown.new_from_strings([choice.label for choice in choices])
        selector.set_selected(choices.index(selected_choice))
        selector.connect("notify::selected", callback)
        row.append(label)
        row.append(selector)
        section.append(row)
    return section


def create_column_view(selection, application):
    """Return the record table bound to *selection*."""
    column_view = Gtk.ColumnView.new(selection)
    column_view.set_hexpand(True)
    column_view.set_vexpand(True)
    # The leading result icon remains visible while long filenames are truncated.
    for title, property_name in TABLE_COLUMNS:
        column = (
            create_icon_column(application)
            if property_name is None
            else create_text_column(title, property_name)
        )
        column_view.append_column(column)
    return column_view


def create_text_column(title, property_name):
    """Create a text column bound to a ``FileItem`` property."""
    factory = Gtk.SignalListItemFactory()

    def setup(_factory, list_item):
        label = Gtk.Label(xalign=0)
        label._binding = None
        list_item.set_child(label)

    def bind(_factory, list_item):
        # Retain each binding to release it when GTK recycles the list item.
        label = list_item.get_child()
        file_item = list_item.get_item()
        label._binding = file_item.bind_property(
            property_name, label, "label", GObject.BindingFlags.SYNC_CREATE
        )

    def unbind(_factory, list_item):
        label = list_item.get_child()
        if label._binding is not None:
            label._binding.unbind()
            label._binding = None

    factory.connect("setup", setup)
    factory.connect("bind", bind)
    factory.connect("unbind", unbind)
    return Gtk.ColumnViewColumn.new(title, factory)


def create_icon_column(application):
    """Create the dynamic result-icon column."""
    factory = Gtk.SignalListItemFactory()

    def setup(_factory, list_item):
        image = Gtk.Image(pixel_size=16)
        image._item = None
        image._icon_handler = None
        list_item.set_child(image)

    def bind(_factory, list_item):
        # Listen for worker-driven status changes while this recycled row is bound.
        image = list_item.get_child()
        image._item = list_item.get_item()

        def update_icon(_item, _property):
            set_image_icon(
                image,
                result_icon(application.icon_set, image._item.props.icon_name),
                20,
            )

        image._icon_handler = image._item.connect("notify::icon-name", update_icon)
        update_icon(image._item, None)

    def unbind(_factory, list_item):
        image = list_item.get_child()
        if image._item is not None:
            image._item.disconnect(image._icon_handler)
            image._item = None
            image._icon_handler = None

    factory.connect("setup", setup)
    factory.connect("bind", bind)
    factory.connect("unbind", unbind)
    return Gtk.ColumnViewColumn.new("Result", factory)


def create_header_button(icon_source, tooltip, action_name):
    """Return a header-bar button with a supplied icon and application action."""
    button = Gtk.Button()
    image = create_icon_image(icon_source, 22)
    button.set_child(image)
    button.set_tooltip_text(tooltip)
    button.set_action_name(action_name)
    return button, image


def create_icon_image(icon_source, pixel_size):
    """Create an image from a bundled SVG path or an active-theme icon name."""
    image = Gtk.Image()
    set_image_icon(image, icon_source, pixel_size)
    return image


def set_image_icon(image, icon_source, pixel_size):
    """Set an image source while retaining a consistent logical icon size."""
    # Bundled SVGs are file-backed; symbolic icons are resolved by the active GTK theme.
    if icon_source.endswith(".svg"):
        image.set_from_file(icon_source)
    else:
        image.set_from_icon_name(icon_source)
    image.set_pixel_size(pixel_size)


def refresh_window_icons(window, application):
    """Refresh header and result images after the icon-set preference changes."""
    for image, name, pixel_size in window._icon_images:
        set_image_icon(
            image,
            header_icon(application.icon_set, name, application.prefers_dark),
            pixel_size,
        )
    for position in range(application.store.get_n_items()):
        application.store.get_item(position).notify("icon-name")

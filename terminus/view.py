import sublime


def panel_window(view):
    for w in sublime.windows():
        for panel in w.panels():
            v = w.find_output_panel(panel.replace("output.", ""))
            if v and v.id() == view.id():
                return w
    return None


def panel_is_visible(view):
    window = panel_window(view)
    if not window:
        return False
    active_panel = window.active_panel()
    if not active_panel:
        return False
    active_view = window.find_output_panel(active_panel.replace("output.", ""))
    return active_view == view


def view_is_visible(view):
    window = view.window()
    if not window:
        return False
    group, _ = window.get_view_index(view)
    return window.active_view_in_group(group) == view


def view_size(view):
    pixel_width, pixel_height = view.viewport_extent()
    pixel_per_line = view.line_height()
    pixel_per_char = view.em_width()

    if pixel_per_line == 0 or pixel_per_char == 0:
        return (0, 0)

    nb_columns = int(pixel_width / pixel_per_char) - 3
    if nb_columns < 1:
        nb_columns = 1

    nb_rows = int(pixel_height / pixel_per_line)
    if nb_rows < 1:
        nb_rows = 1

    return (nb_rows, nb_columns)

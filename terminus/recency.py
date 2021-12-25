import logging

from .const import EXEC_PANEL
from .terminal import Terminal
from .view import get_panel_window

logger = logging.getLogger('Terminus')


class RecencyManager:
    cycling_panels = False
    _recent_panel = {}
    _recent_view = {}

    @classmethod
    def set_recent_terminal(cls, view):
        terminal = Terminal.from_id(view.id())
        if not terminal:
            return
        logger.debug("set recent view: {}".format(view.id()))
        if terminal.show_in_panel and terminal.panel_name != EXEC_PANEL:
            window = get_panel_window(view)
            if window:
                cls._recent_panel[window.id()] = terminal.panel_name
                cls._recent_view[window.id()] = view
        else:
            window = view.window()
            if window:
                cls._recent_view[window.id()] = view

    @classmethod
    def recent_panel(cls, window):
        if not window:
            return
        try:
            panel_name = cls._recent_panel[window.id()]
            view = window.find_output_panel(panel_name)
            if view and Terminal.from_id(view.id()):
                return panel_name
        except KeyError:
            return

    @classmethod
    def recent_view(cls, window):
        if not window:
            return
        try:
            view = cls._recent_view[window.id()]
            if view:
                terminal = Terminal.from_id(view.id())
                if terminal:
                    return view
        except KeyError:
            return

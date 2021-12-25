import logging

from .const import EXEC_PANEL
from .terminal import Terminal
from .view import get_panel_window

logger = logging.getLogger('Terminus')


class RecencyManager:
    _instances = {}

    @classmethod
    def from_window(cls, window):
        if window.id() in cls._instances:
            return cls._instances[window.id()]
        instance = cls(window)
        cls._instances[window.id()] = instance
        return instance

    @classmethod
    def from_view(cls, view):
        window = get_panel_window(view)
        if not window:
            window = view.window()
        return cls.from_window(window)

    def __init__(self, window):
        self.window = window
        self.cycling_panels = False
        self._recent_panel = None
        self._recent_view = None

    def set_recent_terminal(self, view):
        window = self.window
        if not window:
            return
        terminal = Terminal.from_id(view.id())
        if not terminal:
            return
        logger.debug("set recent view: {}".format(view.id()))
        if terminal.show_in_panel and terminal.panel_name != EXEC_PANEL:
            self._recent_panel = terminal.panel_name
            self._recent_view = view
        else:
            self._recent_view = view

    def recent_panel(self):
        window = self.window
        if not window:
            return
        panel_name = self._recent_panel
        if panel_name:
            view = window.find_output_panel(panel_name)
            if view and Terminal.from_id(view.id()):
                return panel_name

    def recent_view(self):
        window = self.window
        if not window:
            return
        view = self._recent_view
        if view:
            terminal = Terminal.from_id(view.id())
            if terminal:
                return view

import sublime

import sys
import logging

from .terminus.commands import (
    TerminusCommandsEventListener,
    TerminusOpenCommand,
    TerminusCloseCommand,
    TerminusKeypressCommand,
    TerminusCopyCommand,
    TerminusPasteCommand,
    TerminusPasteFromHistoryCommand,
    TerminusDeleteWordCommand,
    ToggleTerminusPanelCommand,
    TerminusSendStringCommand
)
from .terminus.edit_settings import (
    TerminusEditSettingsListener,
    TerminusEditSettingsCommand
)
from .terminus.mouse import (
    TerminusMouseEventListener,
    TerminusOpenContextUrlCommand,
    TerminusClickCommand,
    TerminusOpenImageCommand
)
from .terminus.query import TerminusQueryContextListener
from .terminus.theme import (
    TerminusSelectThemeCommand,
    TerminusGenerateThemeCommand,
    plugin_loaded as theme_plugin_loaded
)
from .terminus.utils import settings_on_change
from .terminus.view import (
    TerminusViewEventListener,
    TerminusActivateCommand,
    TerminusRenderCommand,
    TerminusShowCursor,
    TerminusInsertCommand
)


__all__ = [
    "TerminusCommandsEventListener", "TerminusOpenCommand", "TerminusCloseCommand",
    "TerminusKeypressCommand", "TerminusCopyCommand", "TerminusPasteCommand",
    "TerminusPasteFromHistoryCommand", "TerminusDeleteWordCommand", "ToggleTerminusPanelCommand",
    "TerminusSendStringCommand",
    "TerminusSelectThemeCommand", "TerminusGenerateThemeCommand",
    "TerminusEditSettingsListener", "TerminusEditSettingsCommand",
    "TerminusMouseEventListener", "TerminusOpenContextUrlCommand", "TerminusClickCommand",
    "TerminusOpenImageCommand",
    "TerminusQueryContextListener",
    "TerminusViewEventListener", "TerminusActivateCommand", "TerminusRenderCommand",
    "TerminusShowCursor", "TerminusInsertCommand"
]


logger = logging.getLogger('Terminus')


def plugin_loaded():
    theme_plugin_loaded()

    if not logger.hasHandlers():
        ch = logging.StreamHandler(sys.stdout)
        logger.addHandler(ch)

    settings = sublime.load_settings("Terminus.sublime-settings")

    def on_change(debug):
        if debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.WARNING)

    on_change(settings.get("debug", False))
    settings_on_change(settings, "debug")(on_change)


def plugin_unloaded():
    # close all terminals
    for w in sublime.windows():
        w.destroy_output_panel("Terminus")
        for view in w.views():
            if view.settings().get("terminus_view"):
                w.focus_view(view)
                w.run_command("close")

import sublime

import sys
import logging

# Clear module cache to force reloading all modules of this package.
prefix = __package__ + "."  # don't clear the base package
for module_name in [
    module_name
    for module_name in sys.modules
    if module_name.startswith(prefix) and module_name != __name__
]:
    del sys.modules[module_name]
del prefix


from .terminus.clipboard import TerminusClipboardHistoryUpdater
from .terminus.commands import (
    TerminusActivateCommand,
    TerminusCancelBuildCommand,
    TerminusClearUndoStackCommand,
    TerminusCloseAllCommand,
    TerminusCloseCommand,
    TerminusCopyCommand,
    TerminusDeleteWordCommand,
    TerminusExecCommand,
    TerminusInitializeViewCommand,
    TerminusKeypressCommand,
    TerminusMaximizeCommand,
    TerminusMinimizeCommand,
    TerminusOpenCommand,
    TerminusPasteCommand,
    TerminusPasteFromHistoryCommand,
    TerminusPasteTextCommand,
    TerminusRenameTitleCommand,
    TerminusResetCommand,
    TerminusSendStringCommand,
    ToggleTerminusPanelCommand
)
from .terminus.event_listeners import (
    TerminusCoreEventListener
)
from .terminus.mouse import (
    TerminusClickCommand,
    TerminusMouseEventListener,
    TerminusOpenContextUrlCommand,
    TerminusOpenImageCommand
)
from .terminus.query import TerminusQueryContextListener
from .terminus.render import (
    TerminusCleanupCommand,
    TerminusRenderCommand,
    TerminusShowCursorCommand
)
from .terminus.theme import (
    TerminusGenerateThemeCommand,
    TerminusSelectThemeCommand,
    plugin_loaded as theme_plugin_loaded,
    plugin_unloaded as theme_plugin_unloaded
)
from .terminus.utils import set_settings_on_change
from .terminus.view import (
    TerminusInsertCommand,
    TerminusNukeCommand,
    TerminusTrimTrailingLinesCommand
)


__all__ = [
    "TerminusActivateCommand",
    "TerminusCancelBuildCommand",
    "TerminusCleanupCommand",
    "TerminusClearUndoStackCommand",
    "TerminusClickCommand",
    "TerminusClipboardHistoryUpdater",
    "TerminusCloseAllCommand",
    "TerminusCloseCommand",
    "TerminusCopyCommand",
    "TerminusCoreEventListener",
    "TerminusDeleteWordCommand",
    "TerminusExecCommand",
    "TerminusGenerateThemeCommand",
    "TerminusInitializeViewCommand",
    "TerminusInsertCommand",
    "TerminusKeypressCommand",
    "TerminusMaximizeCommand",
    "TerminusMinimizeCommand",
    "TerminusMouseEventListener",
    "TerminusNukeCommand",
    "TerminusOpenCommand",
    "TerminusOpenContextUrlCommand",
    "TerminusOpenImageCommand",
    "TerminusPasteCommand",
    "TerminusPasteFromHistoryCommand",
    "TerminusPasteTextCommand",
    "TerminusQueryContextListener",
    "TerminusRenameTitleCommand",
    "TerminusRenderCommand",
    "TerminusResetCommand",
    "TerminusSelectThemeCommand",
    "TerminusSendStringCommand",
    "TerminusShowCursorCommand",
    "TerminusTrimTrailingLinesCommand",
    "ToggleTerminusPanelCommand"
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
    set_settings_on_change(settings, "debug", on_change)


def plugin_unloaded():
    # close all terminals
    for w in sublime.windows():
        w.run_command("terminus_close_all")

    theme_plugin_unloaded()
    settings = sublime.load_settings("Terminus.sublime-settings")
    set_settings_on_change(settings, "debug", None)

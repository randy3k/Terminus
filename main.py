import sublime

import sys
import logging

# from PackageDev
# https://github.com/SublimeText/PackageDev/blob/35a68969f94459d38341ea373ab2e583e60d8cda/main.py
try:
    from package_control import events
except ImportError:
    pass
else:
    if events.post_upgrade(__package__):
        # clean up sys.modules to ensure all submodules are reloaded
        prefix = __package__ + "."  # don't clear the base package
        modules_to_clear = {
            module_name
            for module_name in sys.modules
            if module_name.startswith(prefix) and module_name != __name__
        }

        print("[{}] Cleaning up {} cached modules after update…"
              .format(__package__, len(modules_to_clear)))
        for module_name in modules_to_clear:
            del sys.modules[module_name]


from .terminus.clipboard import TerminusClipboardHistoryUpdater
from .terminus.commands import (
    TerminusActivateCommand,
    TerminusCancelBuildCommand,
    TerminusClearUndoStackCommand,
    TerminusCloseAllCommand,
    TerminusCloseCommand,
    TerminusCopyCommand,
    TerminusCoreEventListener,
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
    TerminusRecencyEventListener,
    TerminusRenameTitleCommand,
    TerminusResetCommand,
    TerminusSendStringCommand,
    ToggleTerminusPanelCommand
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
from .terminus.utils import settings_on_change
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
    "TerminusRecencyEventListener",
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
    settings_on_change(settings, "debug")(on_change)


def plugin_unloaded():
    # close all terminals
    for w in sublime.windows():
        w.run_command("terminus_close_all")

    theme_plugin_unloaded()
    settings = sublime.load_settings("Terminus.sublime-settings")
    settings_on_change(settings, "debug", clear=True)

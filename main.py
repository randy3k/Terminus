import sublime

import sys
import logging

# from PackageDev
# https://github.com/SublimeText/PackageDev/blob/20a4966c60c487b30badd2dac9238872e6918af3/main.py
try:
    from package_control import events
except ImportError:
    pass
else:
    if events.post_upgrade(__package__):
        # clean up sys.modules to ensure all submodules are reloaded
        modules_to_clear = set()
        prefix = __package__ + "."  # don't clear the base package
        for module_name in sys.modules:
            if module_name.startswith(prefix) and module_name != __name__:
                modules_to_clear.add(module_name)

        print("[{}] Cleaning up {} cached modules after update…"
              .format(__package__, len(modules_to_clear)))
        for module_name in modules_to_clear:
            del sys.modules[module_name]


from .terminus.commands import (
    TerminusCommandsEventListener,
    TerminusOpenCommand,
    TerminusCloseCommand,
    TerminusCloseAllCommand,
    TerminusViewEventListener,
    TerminusInitializeCommand,
    TerminusActivateCommand,
    TerminusResetCommand,
    TerminusMaximizeCommand,
    TerminusMinimizeCommand,
    TerminusRenderCommand,
    TerminusKeypressCommand,
    TerminusCopyCommand,
    TerminusPasteCommand,
    TerminusPasteFromHistoryCommand,
    TerminusDeleteWordCommand,
    ToggleTerminusPanelCommand,
    TerminusSendStringCommand,
    TerminusShowCursor,
    TerminusInsertCommand
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
    plugin_loaded as theme_plugin_loaded,
    plugin_unloaded as theme_plugin_unloaded
)
from .terminus.utils import settings_on_change


__all__ = [
    "TerminusCommandsEventListener", "TerminusOpenCommand", "TerminusCloseCommand",
    "TerminusCloseAllCommand",
    "TerminusViewEventListener", "TerminusInitializeCommand", "TerminusActivateCommand",
    "TerminusResetCommand", "TerminusMaximizeCommand", "TerminusMinimizeCommand",
    "TerminusRenderCommand", "TerminusKeypressCommand", "TerminusCopyCommand",
    "TerminusPasteCommand", "TerminusShowCursor", "TerminusInsertCommand",
    "TerminusPasteFromHistoryCommand", "TerminusDeleteWordCommand", "ToggleTerminusPanelCommand",
    "TerminusSendStringCommand",
    "TerminusSelectThemeCommand", "TerminusGenerateThemeCommand",
    "TerminusEditSettingsListener", "TerminusEditSettingsCommand",
    "TerminusMouseEventListener", "TerminusOpenContextUrlCommand", "TerminusClickCommand",
    "TerminusOpenImageCommand",
    "TerminusQueryContextListener"
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

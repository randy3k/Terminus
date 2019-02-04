import sublime

import sys
import logging

try:
    from .terminus.commands import (
        TerminusCommandsEventListener,
        TerminusOpenCommand,
        TerminusCloseCommand,
        TerminusCloseAllCommand,
        TerminusViewEventListener,
        TerminusInitializeCommand,
        TerminusActivateCommand,
        TerminusClearHistoryCommand,
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
except ImportError:
    pass

__all__ = [
    "TerminusCommandsEventListener", "TerminusOpenCommand", "TerminusCloseCommand",
    "TerminusCloseAllCommand",
    "TerminusViewEventListener", "TerminusInitializeCommand", "TerminusActivateCommand",
    "TerminusClearHistoryCommand", "TerminusMaximizeCommand", "TerminusMinimizeCommand",
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
    try:
        from package_control import events
        if events.post_upgrade(__package__):
            from .tools.reloader import reload_package
            reload_package(__package__)
    except ImportError:
        pass

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

import sublime
import sublime_plugin

import logging
import difflib
from random import random

from .clipboard import g_clipboard_history
from .recency import RecencyManager
from .terminal import Terminal

logger = logging.getLogger('Terminus')


class TerminusCoreEventListener(sublime_plugin.EventListener):

    def on_activated_async(self, view):
        recency_manager = RecencyManager.from_view(view)
        if not recency_manager:
            return

        if not view.settings().get("terminus_view", False):
            recency_manager.cycling_panels = False
            return

        if random() > 0.7:
            # occassionally cull zombie terminals
            Terminal.cull_terminals()
            # clear undo stack
            view.run_command("terminus_clear_undo_stack")

        terminal = Terminal.from_id(view.id())
        if terminal:
            recency_manager.set_recent_terminal(view)
            return

        settings = view.settings()
        if not settings.has("terminus_view.args"):
            return

        if settings.get("terminus_view.finished", False):
            return

        kwargs = settings.get("terminus_view.args")
        if "cmd" not in kwargs:
            return

        settings = sublime.load_settings("Terminus.sublime-settings")
        if settings.get("reactivate_terminals", True) is not True:
            return

        if view.settings().get("terminus_view.reactivable", False):
            sublime.set_timeout(lambda: view.run_command("terminus_activate", kwargs), 100)

    def on_pre_close(self, view):
        # panel doesn't trigger on_pre_close
        terminal = Terminal.from_id(view.id())
        if terminal:
            terminal.kill()

    def on_modified(self, view):
        # to catch unicode input
        terminal = Terminal.from_id(view.id())
        if not terminal or not terminal.process.isalive():
            return
        command, args, _ = view.command_history(0)
        if command.startswith("terminus"):
            return
        elif command == "insert" and "characters" in args and \
                len(view.sel()) == 1 and view.sel()[0].empty():
            chars = args["characters"]
            current_cursor = view.sel()[0].end()
            region = sublime.Region(
                max(current_cursor - len(chars), self._cursor), current_cursor)
            text = view.substr(region)
            self._cursor = current_cursor
            logger.debug("text {} detected".format(text))
            view.run_command("terminus_paste_text", {"text": text, "bracketed": False})
        elif command:
            logger.debug("undo {}".format(command))
            view.run_command("soft_undo")

    def on_selection_modified(self, view):
        terminal = Terminal.from_id(view.id())
        if not terminal or not terminal.process.isalive():
            return
        if len(view.sel()) != 1 or not view.sel()[0].empty():
            return
        self._cursor = view.sel()[0].end()

    def on_text_command(self, view, name, args):
        if not view.settings().get('terminus_view'):
            return
        if name == "copy":
            return ("terminus_copy", None)
        elif name == "paste":
            return ("terminus_paste", None)
        elif name == "paste_and_indent":
            return ("terminus_paste", None)
        elif name == "paste_from_history":
            return ("terminus_paste_from_history", None)
        elif name == "paste_selection_clipboard":
            self._pre_paste = view.substr(view.visible_region())
        elif name == "undo":
            return ("noop", None)

    def on_post_text_command(self, view, name, args):
        if not view.settings().get('terminus_view'):
            return
        if name == 'terminus_copy':
            g_clipboard_history.push_text(sublime.get_clipboard())
        elif name == "paste_selection_clipboard":
            added = [
                df[2:] for df in difflib.ndiff(self._pre_paste, view.substr(view.visible_region()))
                if df[0] == '+']
            view.run_command("terminus_paste_text", {"text": "".join(added)})

    def on_window_command(self, window, command_name, args):
        if command_name == "show_panel":
            panel = args["panel"].replace("output.", "")
            view = window.find_output_panel(panel)
            if view:
                terminal = Terminal.from_id(view.id())
                if terminal and terminal.show_in_panel:
                    recency_manager = RecencyManager.from_view(view)
                    if recency_manager:
                        recency_manager.set_recent_terminal(view)

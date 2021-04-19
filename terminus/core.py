import sublime
import sublime_plugin

import os
import re
import sys
import math
import time
import logging
from random import random

from .clipboard import g_clipboard_history
from .key import get_key_code
from .terminal import Terminal, CONTINUATION
from .ptty import segment_buffer_line
from .utils import shlex_split
from .utils import available_panel_name, rev_wcwidth, highlight_key
from .view import panel_window, panel_is_visible, view_is_visible
from .theme import get_theme


KEYS = [
    "ctrl+k",
    "ctrl+p"
]

DEFAULT_PANEL = "Terminus"
EXEC_PANEL = "Terminus Build Results"

logger = logging.getLogger('Terminus')


class TerminusCoreEventListener(sublime_plugin.EventListener):

    def on_pre_close(self, view):
        # panel doesn't trigger on_pre_close
        terminal = Terminal.from_id(view.id())
        if terminal:
            terminal.close()

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
                max(current_cursor - len(chars), self.cursor), current_cursor)
            text = view.substr(region)
            self.cursor = current_cursor
            logger.debug("text {} detected".format(text))
            terminal.send_string(text)
        elif command:
            logger.debug("undo {}".format(command))
            view.run_command("soft_undo")

    def on_selection_modified(self, view):
        terminal = Terminal.from_id(view.id())
        if not terminal or not terminal.process.isalive():
            return
        if len(view.sel()) != 1 or not view.sel()[0].empty():
            return
        self.cursor = view.sel()[0].end()

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
        elif name == "undo":
            return ("noop", None)

    def on_post_text_command(self, view, name, args):
        """
        help panel terminal to capture copied text
        """
        if not view.settings().get('terminus_view'):
            return

        if name == 'terminus_copy':
            g_clipboard_history.push_text(sublime.get_clipboard())


class TerminusOpenCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        sublime.set_timeout_async(lambda: self.run_async(**kwargs))

    def run_async(
            self,
            config_name=None,
            cmd=None,
            shell_cmd=None,
            cwd=None,
            working_dir=None,
            env={},
            title=None,
            panel_name=None,
            focus=True,
            tag=None,
            file_regex=None,
            line_regex=None,
            pre_window_hooks=[],
            post_window_hooks=[],
            post_view_hooks=[],
            auto_close=True,
            cancellable=False,
            timeit=False):
        config = None

        st_vars = self.window.extract_variables()

        if config_name == "<ask>":
            self.show_configs()
            return

        if config_name:
            config = self.get_config_by_name(config_name)
        else:
            config = self.get_config_by_name("Default")
        config_name = config["name"]

        if "cmd" in config and "shell_cmd" in config:
            raise Exception(
                "both `cmd` are `shell_cmd` are specified in config {}".format(config_name))

        if cmd and shell_cmd:
            raise Exception("both `cmd` are `shell_cmd` are passed to terminus_open")

        if shell_cmd is not None or ("shell_cmd" in config and config["shell_cmd"] is not None):
            if shell_cmd is None:
                shell_cmd = config["shell_cmd"]

            if not isinstance(shell_cmd, str):
                raise ValueError("shell_cmd should be a string")
            # mimic exec target
            if sys.platform.startswith("win"):
                comspec = os.environ.get("COMSPEC", "cmd.exe")
                cmd_to_run = [comspec, "/c"] + shlex_split(shell_cmd)
            elif sys.platform == "darwin":
                cmd_to_run = ["/usr/bin/env", "bash", "-l", "-c", shell_cmd]
            else:
                cmd_to_run = ["/usr/bin/env", "bash", "-c", shell_cmd]

        elif cmd is not None or ("cmd" in config and config["cmd"] is not None):

            if cmd is None:
                cmd = config["cmd"]

            cmd_to_run = cmd

        else:
            raise Exception("both `cmd` are `shell_cmd` are empty")

        if cmd_to_run is None:
            raise ValueError("cannot determine command to run")

        if isinstance(cmd_to_run, str):
            cmd_to_run = [cmd_to_run]

        cmd_to_run = sublime.expand_variables(cmd_to_run, st_vars)

        if env:
            config["env"] = env

        if "env" in config:
            _env = config["env"]
        else:
            _env = {}

        _env["TERMINUS_SUBLIME"] = "1"  # for backward compatibility
        _env["TERM_PROGRAM"] = "Terminus-Sublime"

        if sys.platform.startswith("win"):
            pass

        else:
            settings = sublime.load_settings("Terminus.sublime-settings")
            if "TERM" not in _env:
                _env["TERM"] = settings.get("unix_term", "linux")

            if _env["TERM"] not in ["linux", "xterm", "xterm-16color", "xterm-256color"]:
                raise Exception("{} is not supported.".format(_env["TERM"]))

            if "LANG" not in _env:
                if "LANG" in os.environ:
                    _env["LANG"] = os.environ["LANG"]
                else:
                    _env["LANG"] = settings.get("unix_lang", "en_US.UTF-8")

        _env.update(env)

        if not cwd and working_dir:
            cwd = working_dir

        if cwd:
            cwd = sublime.expand_variables(cwd, st_vars)

        if not cwd:
            if self.window.folders():
                cwd = self.window.folders()[0]
            else:
                cwd = os.path.expanduser("~")

        if not os.path.isdir(cwd):
            home = os.path.expanduser("~")
            if home:
                cwd = home

        if not os.path.isdir(cwd):
            raise Exception("{} does not exist".format(cwd))

        terminal = Terminal.from_tag(tag) if tag else None
        terminus_view = terminal.view if terminal else None
        window = terminus_view.window() if terminus_view else self.window

        if not terminus_view and panel_name:
            if panel_name == DEFAULT_PANEL:
                panel_name = available_panel_name(window, panel_name)

            terminus_view = window.get_output_panel(panel_name)

        if terminus_view:
            terminal = Terminal.from_id(terminus_view.id())
            if terminal:
                terminal.close()
            terminus_view.run_command("terminus_nuke")
            terminus_view.settings().erase("terminus_view")
            terminus_view.settings().erase("terminus_view.closed")
            terminus_view.settings().erase("terminus_view.viewport_y")

        # pre_window_hooks
        for hook in pre_window_hooks:
            window.run_command(*hook)

        if not terminus_view:
            terminus_view = window.new_file()

        terminus_view.run_command(
            "terminus_activate",
            {
                "config_name": config_name,
                "cmd": cmd_to_run,
                "cwd": cwd,
                "env": _env,
                "title": title,
                "panel_name": panel_name,
                "tag": tag,
                "auto_close": auto_close,
                "cancellable": cancellable,
                "timeit": timeit,
                "file_regex": file_regex,
                "line_regex": line_regex
            })

        if panel_name:
            window.run_command("show_panel", {"panel": "output.{}".format(panel_name)})

        if focus:
            window.focus_view(terminus_view)

        # post_window_hooks
        for hook in post_window_hooks:
            window.run_command(*hook)

        # post_view_hooks
        for hook in post_view_hooks:
            terminus_view.run_command(*hook)

    def show_configs(self):
        settings = sublime.load_settings("Terminus.sublime-settings")
        configs = settings.get("shell_configs", [])

        ok_configs = []
        has_default = False
        platform = sublime.platform()
        for config in configs:
            if "enable" in config and not config["enable"]:
                continue
            if "platforms" in config and platform not in config["platforms"]:
                continue
            if "default" in config and config["default"] and not has_default:
                has_default = True
                ok_configs = [config] + ok_configs
            else:
                ok_configs.append(config)

        if not has_default:
            default_config = self._default_config()
            ok_configs = [default_config] + ok_configs

        self.window.show_quick_panel(
            [[config["name"],
              config["cmd"] if isinstance(config["cmd"], str) else config["cmd"][0]]
             for config in ok_configs],
            lambda x: on_selection_shell(x)
        )

        def on_selection_shell(index):
            if index < 0:
                return
            config = ok_configs[index]
            config_name = config["name"]
            sublime.set_timeout(
                lambda: self.window.show_quick_panel(
                    ["Open in Tab", "Open in Panel"],
                    lambda x: on_selection_method(x, config_name)
                )
            )

        def on_selection_method(index, config_name):
            if index == 0:
                self.run(config_name=config_name)
            elif index == 1:
                self.run(config_name=config_name, panel_name=DEFAULT_PANEL)

    def get_config_by_name(self, name):
        default_config = self.default_config()
        if name.lower() == "default":
            return default_config

        settings = sublime.load_settings("Terminus.sublime-settings")
        configs = settings.get("shell_configs", [])

        platform = sublime.platform()
        for config in configs:
            if "enable" in config and not config["enable"]:
                continue
            if "platforms" in config and platform not in config["platforms"]:
                continue
            if name.lower() == config["name"].lower():
                return config

        # last chance
        if name.lower() == default_config["name"].lower():
            return default_config
        raise Exception("Config {} not found".format(name))

    def default_config(self):
        settings = sublime.load_settings("Terminus.sublime-settings")
        configs = settings.get("shell_configs", [])

        platform = sublime.platform()
        for config in configs:
            if "enable" in config and not config["enable"]:
                continue
            if "platforms" in config and platform not in config["platforms"]:
                continue
            if "default" in config and config["default"]:
                return config

        default_config_name = settings.get("default_config", None)
        if isinstance(default_config_name, dict):
            if platform in default_config_name:
                default_config_name = default_config_name[platform]
            else:
                default_config_name = None

        if default_config_name:
            for config in configs:
                if "enable" in config and not config["enable"]:
                    continue
                if "platforms" in config and platform not in config["platforms"]:
                    continue
                if default_config_name.lower() == config["name"].lower():
                    return config

        return self._default_config()

    def _default_config(self):
        if sys.platform.startswith("win"):
            return {
                "name": "Command Prompt",
                "cmd": "cmd.exe",
                "env": {}
            }
        else:
            if "SHELL" in os.environ:
                shell = os.environ["SHELL"]
                if os.path.basename(shell) == "tcsh":
                    cmd = [shell, "-l"]
                else:
                    cmd = [shell, "-i", "-l"]
            else:
                cmd = ["/bin/bash", "-i", "-l"]

            return {
                "name": "Login Shell",
                "cmd": cmd,
                "env": {}
            }


class TerminusCloseCommand(sublime_plugin.TextCommand):

    def run(self, _):
        view = self.view
        if not view.settings().get("terminus_view"):
            return

        terminal = Terminal.from_id(view.id())
        if terminal:
            terminal.close()
            panel_name = terminal.panel_name
            if panel_name:
                window = panel_window(view)
                if window:
                    window.destroy_output_panel(panel_name)
            else:
                view.close()


class TerminusCloseAllCommand(sublime_plugin.WindowCommand):

    def run(self):
        window = self.window
        views = []
        for view in window.views():
            if view.settings().get("terminus_view"):
                views.append(view)
        for panel in window.panels():
            view = window.find_output_panel(panel.replace("output.", ""))
            if view and view.settings().get("terminus_view"):
                views.append(view)
        for view in views:
            view.run_command("terminus_close")


# a drop in replacement of target `exec` in sublime-build
class TerminusExecCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        if "kill" in kwargs and kwargs["kill"]:
            self.window.run_command("terminus_cancel_build")
            return

        if "cmd" not in kwargs and "shell_cmd" not in kwargs:
            raise Exception("'cmd' or 'shell_cmd' is required")
        if "panel_name" in kwargs:
            raise Exception("'panel_name' must not be specified")
        if "tag" in kwargs:
            raise Exception("'tag' must not be specified")
        kwargs["panel_name"] = EXEC_PANEL
        if "focus" not in kwargs:
            kwargs["focus"] = False
        if "auto_close" not in kwargs:
            kwargs["auto_close"] = False
        if "cancellable" not in kwargs:
            kwargs["cancellable"] = True
        if "timeit" not in kwargs:
            kwargs["timeit"] = True
        for key in ["encoding", "quiet", "word_wrap", "syntax"]:
            if key in kwargs:
                del kwargs[key]
        self.window.run_command("terminus_open", kwargs)


class TerminusCancelBuildCommand(sublime_plugin.WindowCommand):
    def run(self, *args, **kwargs):
        window = self.window
        for panel_name in window.panels():
            panel_name = panel_name.replace("output.", "")
            if panel_name != EXEC_PANEL:
                continue
            view = window.find_output_panel(panel_name)
            if not view:
                continue
            terminal = Terminal.from_id(view.id())
            if not terminal:
                continue
            if terminal.cancellable:
                terminal.cleanup(by_user=True)


class TerminusRecencyEventListener(sublime_plugin.EventListener):
    _recent_panel = {}
    _recent_view = {}
    _active_view = {}

    def on_activated_async(self, view):
        if view.settings().get("is_widget", False) and \
                not view.settings().get("terminus_view", False):
            return

        if random() > 0.7:
            # occassionally cull zombie terminals
            Terminal.cull_terminals()

        window = view.window()
        if window:
            TerminusRecencyEventListener._active_view[window.id()] = view

        terminal = Terminal.from_id(view.id())
        if terminal:
            TerminusRecencyEventListener.set_recent_terminal(view)
            return

        settings = view.settings()
        if not settings.has("terminus_view.args") or settings.get("terminus_view.detached"):
            return

        if settings.get("terminus_view.closed", False):
            return

        kwargs = settings.get("terminus_view.args")
        if "cmd" not in kwargs:
            return

        sublime.set_timeout(lambda: view.run_command("terminus_activate", kwargs), 100)

    def on_window_command(self, window, command_name, args):
        if command_name == "show_panel":
            panel = args["panel"].replace("output.", "")
            view = window.find_output_panel(panel)
            if view:
                terminal = Terminal.from_id(view.id())
                if terminal and terminal.panel_name:
                    TerminusRecencyEventListener.set_recent_terminal(view)

    @classmethod
    def set_recent_terminal(cls, view):
        terminal = Terminal.from_id(view.id())
        if not terminal:
            return
        logger.debug("set recent view: {}".format(view.id()))
        panel_name = terminal.panel_name
        if panel_name and panel_name != EXEC_PANEL:
            window = panel_window(view)
            if window:
                cls._recent_panel[window.id()] = panel_name
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

    @classmethod
    def active_view(cls, window):
        if not window:
            return
        try:
            view = cls._active_view[window.id()]
            if view:
                terminal = Terminal.from_id(view.id())
                if terminal:
                    return view
        except KeyError:
            return


class TerminusInitializeCommand(sublime_plugin.TextCommand):
    def run(self, _, **kwargs):
        view = self.view
        view_settings = view.settings()

        if view_settings.get("terminus_view", False):
            return

        view_settings.set("terminus_view", True)
        view_settings.set("terminus_view.args", kwargs)

        terminus_settings = sublime.load_settings("Terminus.sublime-settings")
        if "panel_name" in kwargs:
            view_settings.set("terminus_view.panel_name", kwargs["panel_name"])
        if "tag" in kwargs:
            view_settings.set("terminus_view.tag", kwargs["tag"])
        if "cancellable" in kwargs:
            view_settings.set("terminus_view.cancellable", kwargs["cancellable"])
        view_settings.set(
            "terminus_view.natural_keyboard",
            terminus_settings.get("natural_keyboard", True))
        preserve_keys = terminus_settings.get("preserve_keys", {})
        if not preserve_keys:
            preserve_keys = terminus_settings.get("disable_keys", {})
        if not preserve_keys:
            preserve_keys = terminus_settings.get("ignore_keys", {})
        for key in KEYS:
            if key not in preserve_keys:
                view_settings.set("terminus_view.key.{}".format(key), True)
        view.set_scratch(True)
        view.set_read_only(False)
        view_settings.set("is_widget", True)
        view_settings.set("gutter", False)
        view_settings.set("highlight_line", False)
        view_settings.set("auto_complete_commit_on_tab", False)
        view_settings.set("draw_centered", False)
        view_settings.set("word_wrap", False)
        view_settings.set("auto_complete", False)
        view_settings.set("draw_white_space", "none")
        view_settings.set("draw_unicode_white_space", False)
        view_settings.set("draw_indent_guides", False)
        # view_settings.set("caret_style", "blink")
        view_settings.set("scroll_past_end", True)

        if get_theme(terminus_settings):
            view_settings.set("color_scheme", "Terminus.hidden-color-scheme")

        max_columns = terminus_settings.get("max_columns")
        if max_columns:
            rulers = view_settings.get("rulers", [])
            if max_columns not in rulers:
                rulers.append(max_columns)
                view_settings.set("rulers", rulers)

        # search
        if "file_regex" in kwargs:
            view_settings.set("result_file_regex", kwargs["file_regex"])
        if "line_regex" in kwargs:
            view_settings.set("result_line_regex", kwargs["line_regex"])
        if "cwd" in kwargs:
            view_settings.set("result_base_dir", kwargs["cwd"])
        # disable bracket highligher (not working)
        view_settings.set("bracket_highlighter.ignore", True)
        view_settings.set("bracket_highlighter.clone_locations", {})
        # disable vintageous
        view_settings.set("__vi_external_disable", True)
        for key, value in terminus_settings.get("view_settings", {}).items():
            view_settings.set(key, value)
        # disable vintage
        view_settings.set("command_mode", False)


class TerminusActivateCommand(sublime_plugin.TextCommand):

    def run(self, _, **kwargs):
        view = self.view
        view.run_command("terminus_initialize", kwargs)
        Terminal.cull_terminals()
        terminal = Terminal(view)
        terminal.activate(
            config_name=kwargs["config_name"],
            cmd=kwargs["cmd"],
            cwd=kwargs["cwd"],
            env=kwargs["env"],
            title=kwargs["title"],
            panel_name=kwargs["panel_name"],
            tag=kwargs["tag"],
            auto_close=kwargs["auto_close"],
            cancellable=kwargs["cancellable"],
            timeit=kwargs["timeit"]
        )
        TerminusRecencyEventListener.set_recent_terminal(view)


class TerminusResetCommand(sublime_plugin.TextCommand):

    def run(self, _, soft=False, **kwargs):
        view = self.view
        terminal = Terminal.from_id(view.id())
        if not terminal:
            return

        if soft:
            view.run_command("terminus_nuke")
            view.settings().erase("terminus_view.viewport_y")
            terminal.set_offset()
            return

        def run_detach():
            terminal.detach_view()

            def run_sync():
                if terminal.panel_name:
                    panel_name = terminal.panel_name
                    window = panel_window(view)
                    window.destroy_output_panel(panel_name)  # do not reuse
                    new_view = window.get_output_panel(panel_name)
                    new_view.run_command("terminus_initialize")

                    def run_attach():
                        terminal.attach_view(new_view)
                        window.run_command("show_panel", {"panel": "output.{}".format(panel_name)})
                        window.focus_view(new_view)
                else:
                    window = view.window()
                    has_focus = view == window.active_view()
                    layout = window.get_layout()
                    if not has_focus:
                        window.focus_view(view)
                    new_view = window.new_file()
                    view.close()
                    new_view.run_command("terminus_initialize")

                    def run_attach():
                        window.run_command("set_layout", layout)
                        if has_focus:
                            window.focus_view(new_view)
                        terminal.attach_view(new_view)

                sublime.set_timeout_async(run_attach)

            sublime.set_timeout(run_sync)

        sublime.set_timeout_async(run_detach)


class TerminusRenameTitleCommand(sublime_plugin.TextCommand):

    def run(self, _, title=None):
        view = self.view
        terminal = Terminal.from_id(view.id())

        terminal.default_title = title
        view.run_command("terminus_render")

    def input(self, _):
        return TemrinusRenameTitleTextInputerHandler(self.view)

    def is_visible(self):
        return bool(Terminal.from_id(self.view.id()))


class TemrinusRenameTitleTextInputerHandler(sublime_plugin.TextInputHandler):
    def __init__(self, view):
        self.view = view
        super().__init__()

    def name(self):
        return "title"

    def initial_text(self):
        terminal = Terminal.from_id(self.view.id())
        return terminal.default_title if terminal else ""

    def placeholder(self):
        return "new title"


class TerminusMaximizeCommand(sublime_plugin.TextCommand):

    def is_enabled(self):
        view = self.view
        terminal = Terminal.from_id(view.id())
        if terminal and terminal.panel_name:
            return True
        else:
            return False

    def run(self, _, **kwargs):
        view = self.view
        terminal = Terminal.from_id(view.id())

        def run_detach():
            all_text = view.substr(sublime.Region(0, view.size()))
            terminal.detach_view()

            def run_sync():
                offset = terminal.offset
                window = panel_window(view)
                window.destroy_output_panel(terminal.panel_name)
                new_view = window.new_file()

                def run_attach():
                    new_view.run_command("terminus_initialize")
                    new_view.run_command(
                        "terminus_insert", {"point": 0, "character": all_text})
                    terminal.panel_name = None
                    terminal.attach_view(new_view, offset)

                sublime.set_timeout_async(run_attach)

            sublime.set_timeout(run_sync)

        sublime.set_timeout_async(run_detach)


def dont_close_windows_when_empty(func):
    def f(*args, **kwargs):
        s = sublime.load_settings('Preferences.sublime-settings')
        close_windows_when_empty = s.get('close_windows_when_empty')
        s.set('close_windows_when_empty', False)
        func(*args, **kwargs)
        if close_windows_when_empty:
            sublime.set_timeout(
                lambda: s.set('close_windows_when_empty', close_windows_when_empty),
                1000)
    return f


class TerminusMinimizeCommand(sublime_plugin.TextCommand):

    def is_enabled(self):
        view = self.view
        terminal = Terminal.from_id(view.id())
        if terminal and not terminal.panel_name:
            return True
        else:
            return False

    def run(self, _, **kwargs):
        view = self.view
        terminal = Terminal.from_id(view.id())

        def run_detach():
            all_text = view.substr(sublime.Region(0, view.size()))
            terminal.detach_view()

            @dont_close_windows_when_empty
            def run_sync():
                offset = terminal.offset
                window = view.window()
                view.close()
                if "panel_name" in kwargs:
                    panel_name = kwargs["panel_name"]
                else:
                    panel_name = view.settings().get("terminus_view.panel_name", None)
                    if not panel_name:
                        panel_name = available_panel_name(window, DEFAULT_PANEL)

                new_view = window.get_output_panel(panel_name)

                def run_attach():
                    terminal.panel_name = panel_name
                    new_view.run_command("terminus_initialize", {"panel_name": panel_name})
                    new_view.run_command(
                        "terminus_insert", {"point": 0, "character": all_text})
                    window.run_command("show_panel", {"panel": "output.{}".format(panel_name)})
                    window.focus_view(new_view)
                    terminal.attach_view(new_view, offset)

                sublime.set_timeout_async(run_attach)

            sublime.set_timeout(run_sync)

        sublime.set_timeout_async(run_detach)


class TerminusKeypressCommand(sublime_plugin.TextCommand):

    def run(self, _, **kwargs):
        terminal = Terminal.from_id(self.view.id())
        if not terminal or not terminal.process.isalive():
            return
        # self.view.run_command("terminus_render")
        self.view.run_command("terminus_show_cursor")
        terminal.send_key(**kwargs)


class TerminusCopyCommand(sublime_plugin.TextCommand):
    """
    It does nothing special now, just `copy`.
    """

    def run(self, edit):
        view = self.view
        if not view.settings().get("terminus_view"):
            return
        text = ""
        for s in view.sel():
            if text:
                text += "\n"
            text += view.substr(s)

        # remove the continuation marker
        text = text.replace(CONTINUATION + "\n", "")
        text = text.replace(CONTINUATION, "")

        sublime.set_clipboard(text)


class TerminusPasteCommand(sublime_plugin.TextCommand):

    def run(self, edit, bracketed=False):
        view = self.view
        terminal = Terminal.from_id(view.id())
        if not terminal:
            return

        bracketed = bracketed or terminal.bracketed_paste_mode_enabled()
        if bracketed:
            terminal.send_key("bracketed_paste_mode_start")

        copied = sublime.get_clipboard()

        # self.view.run_command("terminus_render")
        self.view.run_command("terminus_show_cursor")

        terminal.send_string(copied)

        if bracketed:
            terminal.send_key("bracketed_paste_mode_end")


class TerminusPasteFromHistoryCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        # provide paste choices
        paste_list = g_clipboard_history.get()
        keys = [x[0] for x in paste_list]
        self.view.show_popup_menu(keys, lambda choice_index: self.paste_choice(choice_index))

    def is_enabled(self):
        return not g_clipboard_history.empty()

    def paste_choice(self, choice_index):
        if choice_index == -1:
            return
        # use normal paste command
        text = g_clipboard_history.get()[choice_index][1]

        # rotate to top
        g_clipboard_history.push_text(text)

        sublime.set_clipboard(text)
        self.view.run_command("terminus_paste")


class TerminusDeleteWordCommand(sublime_plugin.TextCommand):
    """
    On Windows, ctrl+backspace and ctrl+delete are used to delete words
    However, there is no standard key to delete word with ctrl+backspace
    a workaround is to repeatedly apply backspace to delete word
    """

    def run(self, edit, forward=False):
        view = self.view
        terminal = Terminal.from_id(view.id())
        if not terminal:
            return

        if len(view.sel()) != 1 or not view.sel()[0].empty():
            return

        if forward:
            pt = view.sel()[0].end()
            line = view.line(pt)
            text = view.substr(sublime.Region(pt, line.end()))
            match = re.search(r"(?<=\w)\b", text)
            if match:
                n = match.span()[0]
                n = n if n > 0 else 1
            else:
                n = 1
            delete_code = get_key_code("delete")

        else:
            pt = view.sel()[0].end()
            line = view.line(pt)
            text = view.substr(sublime.Region(line.begin(), pt))
            matches = list(re.finditer(r"\b(?=\w)", text))
            if matches:
                for match in matches:
                    pass
                n = view.rowcol(pt)[1] - match.span()[0]
                n if n > 0 else 1
            else:
                n = 1
            delete_code = get_key_code("backspace")

        # self.view.run_command("terminus_render")
        self.view.run_command("terminus_show_cursor")

        terminal.send_string(delete_code * n)


class ToggleTerminusPanelCommand(sublime_plugin.WindowCommand):

    def run(self, **kwargs):
        window = self.window
        if "panel_name" in kwargs:
            panel_name = kwargs["panel_name"]
        else:
            panel_name = TerminusRecencyEventListener.recent_panel(window) or DEFAULT_PANEL
            kwargs["panel_name"] = panel_name

        terminus_view = window.find_output_panel(panel_name)
        if terminus_view:
            window.run_command(
                "show_panel", {"panel": "output.{}".format(panel_name), "toggle": True})
            window.focus_view(terminus_view)
        else:
            window.run_command("terminus_open", kwargs)


class TerminusFindTerminalMixin:

    def find_terminal(self, window, tag=None, panel_only=False, visible_only=False):
        if tag:
            terminal = Terminal.from_tag(tag)
            if terminal:
                view = terminal.view
        else:
            view = TerminusRecencyEventListener.active_view(window)
            if view and panel_only:
                terminal = Terminal.from_id(view.id())
                if not terminal or not terminal.panel_name:
                    view = None
            if not view:
                view = self.get_terminus_panel(window, visible_only=True)
            if not view and not panel_only:
                view = self.get_terminus_view(window, visible_only=True)
            if not view:
                # get visible recent panel / view
                if panel_only:
                    panel_name = TerminusRecencyEventListener.recent_panel(window)
                    if visible_only and panel_name:
                        view = window.get_output_panel(panel_name)
                        if view:
                            terminal = Terminal.from_id(view.id())
                            if not terminal or not panel_is_visible(view):
                                view = None
                else:
                    view = TerminusRecencyEventListener.recent_view(window)
                    if visible_only and view:
                        terminal = Terminal.from_id(view.id())
                        if terminal:
                            if terminal.panel_name:
                                if not panel_is_visible(view):
                                    view = None
                            else:
                                if not view_is_visible(view):
                                    view = None
            if not visible_only:
                if not view:
                    view = self.get_terminus_panel(window, visible_only=False)
                if not panel_only and not view:
                    view = self.get_terminus_view(window, visible_only=False)

        if view:
            terminal = Terminal.from_id(view.id())
        else:
            terminal = None

        return terminal

    def get_terminus_panel(self, window, visible_only=False):
        if visible_only:
            active_panel = window.active_panel()
            panels = [active_panel] if active_panel else []
        else:
            panels = window.panels()
        for panel in panels:
            panel_name = panel.replace("output.", "")
            if panel_name == EXEC_PANEL:
                continue
            panel_view = window.find_output_panel(panel_name)
            if panel_view:
                terminal = Terminal.from_id(panel_view.id())
                if terminal:
                    return panel_view
        return None

    def get_terminus_view(self, window, visible_only=False):
        for view in window.views():
            if visible_only:
                if not view_is_visible(view):
                    continue
            terminal = Terminal.from_id(view.id())
            if terminal:
                return view


class TerminusSendStringCommand(TerminusFindTerminalMixin, sublime_plugin.WindowCommand):
    """
    Send string to a (tagged) terminal
    """

    def run(self, string, tag=None, visible_only=False):
        terminal = self.find_terminal(self.window, tag=tag, visible_only=visible_only)

        if not terminal:
            raise Exception("no terminal found")
        elif not terminal.process.isalive():
            raise Exception("process is terminated")

        if terminal.panel_name:
            self.window.run_command("show_panel", {
                "panel": "output.{}".format(terminal.panel_name)
            })
        else:
            self.bring_view_to_topmost(terminal.view)

        # terminal.view.run_command("terminus_render")
        terminal.view.run_command("terminus_show_cursor")
        terminal.send_string(string)

    def bring_view_to_topmost(self, view):
        # move the view to the top of the group
        if not view_is_visible(view):
            window = view.window()
            if window:
                window_active_view = window.active_view()
                window.focus_view(view)

                # do not refocus if view and active_view are of the same group
                group, _ = window.get_view_index(view)
                if window.get_view_index(window_active_view)[0] != group:
                    window.focus_view(window_active_view)


# TODO: consolidate the following code with terminal.Terminal

class TerminusViewMixin:

    def ensure_position(self, edit, row, col=0):
        view = self.view
        lastrow = view.rowcol(view.size())[0]
        if lastrow < row:
            view.insert(edit, view.size(), "\n" * (row - lastrow))
        line_region = view.line(view.text_point(row, 0))
        lastcol = view.rowcol(line_region.end())[1]
        if lastcol < col:
            view.insert(edit, line_region.end(), " " * (col - lastcol))


class TerminusRenderCommand(sublime_plugin.TextCommand, TerminusViewMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # it keeps all the highlight keys
        self.colored_lines = {}

    def run(self, edit):
        view = self.view
        startt = time.time()
        terminal = Terminal.from_id(view.id())
        if not terminal:
            return

        screen = terminal.screen

        if terminal._pending_to_clear_scrollback[0]:
            view.replace(edit, sublime.Region(0, view.size()), "")  # nuke everything
            terminal.offset = 0
            terminal.clean_images()
            terminal._pending_to_clear_scrollback[0] = False

        if terminal._pending_to_reset[0]:
            def _reset():
                logger.debug("reset terminal")
                view.run_command("terminus_reset", {"soft": True})
                terminal._pending_to_reset[0] = False

            sublime.set_timeout(_reset)

        self.update_lines(edit, terminal)
        viewport_y = view.settings().get("terminus_view.viewport_y", 0)
        if viewport_y < view.viewport_position()[1] + view.line_height():
            self.trim_trailing_spaces(edit, terminal)
            self.trim_history(edit, terminal)
            view.run_command("terminus_show_cursor")

        if terminal.default_title:
            terminal.title = terminal.default_title
        elif screen.title != terminal.title:
            terminal.title = screen.title

        # we should not clear dirty lines here, it shoud be done in the eventloop
        # screen.dirty.clear()
        logger.debug("updating lines takes {}s".format(str(time.time() - startt)))
        logger.debug("mode: {}, cursor: {}.{}".format(
            [m >> 5 for m in screen.mode], screen.cursor.x, screen.cursor.y))

    def update_lines(self, edit, terminal):
        # cursor = screen.cursor
        screen = terminal.screen
        columns = screen.columns
        dirty_lines = sorted(screen.dirty)
        if dirty_lines:
            # replay history
            history = screen.history
            terminal.offset += len(history)
            offset = terminal.offset
            logger.debug("add {} line(s) to scroll back history".format(len(history)))

            for line in range(len(history)):
                buffer_line = history.pop()
                lf = buffer_line[columns - 1].linefeed
                self.update_line(edit, offset - line - 1, buffer_line, lf)

            # update dirty line¡s
            logger.debug("screen is dirty: {}".format(str(dirty_lines)))
            for line in dirty_lines:
                buffer_line = screen.buffer[line]
                lf = buffer_line[columns - 1].linefeed
                self.update_line(edit, line + offset, buffer_line, lf)

    def update_line(self, edit, line, buffer_line, lf):
        view = self.view
        # make sure the view has enough lines
        self.ensure_position(edit, line)
        line_region = view.line(view.text_point(line, 0))
        segments = list(segment_buffer_line(buffer_line))

        text = "".join(s[0] for s in segments)
        if lf:
            # append a zero width space if the the line ends with a linefeed
            # we will use it to do non-break copying and searching
            # this hack is much easier than rewraping the lines
            text += CONTINUATION

        text = text.rstrip()
        self.decolorize_line(line)
        view.replace(edit, line_region, text)
        self.colorize_line(edit, line, segments)

    def colorize_line(self, edit, line, segments):
        view = self.view
        if segments:
            # ensure the last segement's position exists
            self.ensure_position(edit, line, segments[-1][2])
            if line not in self.colored_lines:
                self.colored_lines[line] = []
        for s in segments:
            fg, bg = s[3:]
            if fg != "default" or bg != "default":
                a = view.text_point(line, s[1])
                b = view.text_point(line, s[2])
                key = highlight_key(view)
                view.add_regions(
                    key,
                    [sublime.Region(a, b)],
                    "terminus.{}.{}".format(fg, bg))
                self.colored_lines[line].append(key)

    def decolorize_line(self, line):
        if line in self.colored_lines:
            for key in self.colored_lines[line]:
                self.view.erase_regions(key)
            del self.colored_lines[line]

    def trim_trailing_spaces(self, edit, terminal):
        view = self.view
        screen = terminal.screen
        cursor = screen.cursor
        cursor_row = terminal.offset + screen.cursor.y
        lastrow = view.rowcol(view.size())[0]
        row = lastrow
        while row > cursor_row:
            line_region = view.line(view.text_point(row, 0))
            text = view.substr(line_region)
            if len(text.strip()) == 0 and \
                    (row not in self.colored_lines or len(self.colored_lines[row]) == 0):
                region = view.line(view.text_point(row, 0))
                view.erase(edit, sublime.Region(region.begin() - 1, region.end()))
                row = row - 1
            else:
                break
        if row == cursor_row:
            line_region = view.line(view.text_point(row, 0))
            text = view.substr(line_region)
            trailing_region = sublime.Region(
                line_region.begin() + rev_wcwidth(text, cursor.x) + 1,
                line_region.end())
            if not trailing_region.empty() and len(view.substr(trailing_region).strip()) == 0:
                view.erase(edit, trailing_region)

    def trim_history(self, edit, terminal):
        """
        If number of lines in view > n, remove n / 10 lines from the top
        """
        view = self.view
        n = sublime.load_settings("Terminus.sublime-settings") \
                   .get("scrollback_history_size", 10000)
        screen = terminal.screen
        lastrow = view.rowcol(view.size())[0]
        if lastrow + 1 > n:
            m = max(lastrow + 1 - n, math.ceil(n / 10))
            logger.debug("removing {} lines from the top".format(m))
            for line in range(m):
                self.decolorize_line(line)
            # shift colored_lines indexes
            self.colored_lines = {k - m: v for (k, v) in self.colored_lines.items()}
            top_region = sublime.Region(0, view.line(view.text_point(m - 1, 0)).end() + 1)
            view.erase(edit, top_region)
            terminal.offset -= m
            lastrow -= m

            # delete outdated images
            terminal.clean_images()

        if lastrow > terminal.offset + screen.lines:
            tail_region = sublime.Region(
                view.text_point(terminal.offset + screen.lines, 0),
                view.size()
            )
            for line in view.lines(tail_region):
                self.decolorize_line(view.rowcol(line.begin())[0])
            view.erase(edit, tail_region)


class TerminusShowCursor(sublime_plugin.TextCommand, TerminusViewMixin):

    def run(self, edit, focus=True, scroll=True):
        view = self.view
        terminal = Terminal.from_id(view.id())
        if not terminal:
            return

        if focus:
            self.focus_cursor(edit, terminal)
        if scroll:
            sublime.set_timeout(lambda: self.scroll_to_cursor(terminal))

    def focus_cursor(self, edit, terminal):
        view = self.view

        sel = view.sel()
        sel.clear()

        screen = terminal.screen
        if screen.cursor.hidden:
            return

        cursor = screen.cursor
        offset = terminal.offset

        if len(view.sel()) > 0 and view.sel()[0].empty():
            row, col = view.rowcol(view.sel()[0].end())
            if row == offset + cursor.y and col == cursor.x:
                return

        # make sure the view has enough lines
        self.ensure_position(edit, cursor.y + offset)

        line_region = view.line(view.text_point(cursor.y + offset, 0))
        text = view.substr(line_region)
        col = rev_wcwidth(text, cursor.x) + 1

        self.ensure_position(edit, cursor.y + offset, col)
        pt = view.text_point(cursor.y + offset, col)

        sel.add(sublime.Region(pt, pt))

    def scroll_to_cursor(self, terminal):
        view = self.view
        last_y = view.text_to_layout(view.size())[1]
        viewport_y = last_y - view.viewport_extent()[1] + view.line_height()
        offset_y = view.text_to_layout(view.text_point(terminal.offset, 0))[1]
        y = max(offset_y, viewport_y)
        view.settings().set("terminus_view.viewport_y", y)
        view.set_viewport_position((0, y), True)

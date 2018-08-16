import sublime
import sublime_plugin

import os
import re
import sys
import logging

from .key import get_key_code
from .terminal import Terminal, CONTINUATION


logger = logging.getLogger('Terminus')


class TerminusCommandsEventListener(sublime_plugin.EventListener):

    @property
    def g_clipboard_history(self):
        import Default
        return Default.paste_from_history.g_clipboard_history

    def on_pre_close(self, view):
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
            self.g_clipboard_history.push_text(sublime.get_clipboard())


class TerminusOpenCommand(sublime_plugin.WindowCommand):

    def run(
            self,
            config_name=None,
            cmd=None,
            cwd=None,
            working_dir=None,
            env={},
            title=None,
            panel_name=None,
            tag=None,
            pre_window_hooks=[],
            post_window_hooks=[],
            post_view_hooks=[],
            auto_close=True):
        config = None

        st_vars = self.window.extract_variables()

        if not config_name and not cmd:
            self.show_configs()
            return

        if config_name:
            config = self.get_config_by_name(config_name)
        else:
            config = {
                "name": "Terminus"
            }
        if cmd:
            config["cmd"] = cmd
        if env:
            config["env"] = env

        cmd = config["cmd"]
        if isinstance(cmd, str):
            cmd = [cmd]

        if cmd:
            cmd = sublime.expand_variables(cmd, st_vars)

        if "env" in config:
            _env = config["env"]
        else:
            _env = {}

        _env["TERMINUS_SUBLIME"] = "1"

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
            raise Exception("{} does not exist".format(cwd))

        if not title:
            title = config["name"]

        # pre_window_hooks
        for hook in pre_window_hooks:
            self.window.run_command(*hook)

        if panel_name:
            self.window.destroy_output_panel(panel_name)  # do not reuse
            terminus_view = self.window.get_output_panel(panel_name)
        else:
            terminus_view = self.window.new_file()

        sublime.set_timeout(lambda: terminus_view.run_command(
            "terminus_activate",
            {
                "cmd": cmd,
                "cwd": cwd,
                "env": _env,
                "title": title,
                "panel_name": panel_name,
                "tag": tag,
                "auto_close": auto_close
            }))

        if panel_name:
            self.window.run_command("show_panel", {"panel": "output.{}".format(panel_name)})
            self.window.focus_view(terminus_view)

        # post_window_hooks
        for hook in post_window_hooks:
            self.window.run_command(*hook)

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
                    ["Open in View", "Open in Panel"],
                    lambda x: on_selection_method(x, config_name)
                )
            )

        def on_selection_method(index, config_name):
            if index == 0:
                self.run(config_name)
            elif index == 1:
                self.run(config_name, panel_name="Terminus")

    def get_config_by_name(self, name):
        default_config = self.default_config()
        if name == "Default":
            return default_config

        settings = sublime.load_settings("Terminus.sublime-settings")
        configs = settings.get("shell_configs", [])

        platform = sublime.platform()
        for config in configs:
            if "enable" in config and not config["enable"]:
                continue
            if "platforms" in config and platform not in config["platforms"]:
                continue
            if name == config["name"]:
                return config

        if name == default_config["name"]:
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
                cmd = [os.environ["SHELL"], "-i", "-l"]
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
        terminal = Terminal.from_id(view.id())
        if terminal:
            terminal.close()
        panel_name = view.settings().get("terminus_view.panel_name")
        if panel_name:
            window = view.window()
            if window:
                window.destroy_output_panel(panel_name)
        else:
            window = view.window()
            if window:
                window.focus_view(view)
                window.run_command("close")


class TerminusKeypressCommand(sublime_plugin.TextCommand):

    def run(self, _, **kwargs):
        terminal = Terminal.from_id(self.view.id())
        if not terminal or not terminal.process.isalive():
            return
        terminal.send_key(**kwargs)
        self.view.run_command("terminus_render")
        self.view.run_command("terminus_show_cursor")


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
        terminal.send_string(copied)

        if bracketed:
            terminal.send_key("bracketed_paste_mode_end")

        self.view.run_command("terminus_render")
        self.view.run_command("terminus_show_cursor")


class TerminusPasteFromHistoryCommand(sublime_plugin.TextCommand):
    @property
    def g_clipboard_history(self):
        import Default
        return Default.paste_from_history.g_clipboard_history

    def run(self, edit):
        # provide paste choices
        paste_list = self.g_clipboard_history.get()
        keys = [x[0] for x in paste_list]
        self.view.show_popup_menu(keys, lambda choice_index: self.paste_choice(choice_index))

    def is_enabled(self):
        return not self.g_clipboard_history.empty()

    def paste_choice(self, choice_index):
        if choice_index == -1:
            return
        # use normal paste command
        text = self.g_clipboard_history.get()[choice_index][1]

        # rotate to top
        self.g_clipboard_history.push_text(text)

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

        terminal.send_string(delete_code * n)

        self.view.run_command("terminus_render")
        self.view.run_command("terminus_show_cursor")


class ToggleTerminusPanelCommand(sublime_plugin.WindowCommand):

    def run(self, **kwargs):
        window = self.window
        if "config_name" not in kwargs:
            kwargs["config_name"] = "Default"
        if "panel_name" in kwargs:
            panel_name = kwargs["panel_name"]
        else:
            panel_name = "Terminus"
            kwargs["panel_name"] = panel_name
        terminus_view = window.find_output_panel(panel_name)
        if terminus_view:
            window.run_command(
                "show_panel", {"panel": "output.{}".format(panel_name), "toggle": True})
            window.focus_view(terminus_view)
        else:
            window.run_command("terminus_open", kwargs)


class TerminusSendStringCommand(sublime_plugin.WindowCommand):
    """
    Send string to a (tagged) terminal
    """

    def run(self, string, tag=None):
        if tag:
            terminal = Terminal.from_tag(tag)
            if terminal:
                view = terminal.view
        else:
            view = self.get_terminus_panel(True)
            if not view:
                view = self.get_terminus_view(True)
            if not view:
                view = self.get_terminus_panel()
            if not view:
                view = self.get_terminus_view()
            if view:
                terminal = Terminal.from_id(view.id())
            else:
                terminal = None

        if not terminal:
            raise Exception("no terminal found")
        elif not terminal.process.isalive():
            raise Exception("process is terminated")

        if view.settings().get("terminus_view.panel_name", None):
            self.window.run_command("show_panel", {
                "panel": "output.{}".format(view.settings().get("terminus_view.panel_name"))
            })
        else:
            self.bring_view_to_topmost(view)

        terminal.send_string(string)
        terminal.view.run_command("terminus_render")
        terminal.view.run_command("terminus_show_cursor")

    def get_terminus_panel(self, visible=False):
        window = self.window
        if visible:
            active_panel = window.active_panel()
            panels = [active_panel] if active_panel else []
        else:
            panels = window.panels()
        for panel in panels:
            panel_view = window.find_output_panel(panel.replace("output.", ""))
            if panel_view:
                terminal = Terminal.from_id(panel_view.id())
                if terminal:
                    return panel_view
        return None

    def get_terminus_view(self, visible=False):
        window = self.window
        for view in window.views():
            if visible:
                group, _ = window.get_view_index(view)
                if window.active_view_in_group(group) != view:
                    continue
            terminal = Terminal.from_id(view.id())
            if terminal:
                return view

    def bring_view_to_topmost(self, view):
        # move the view to the top of the group
        window = view.window()
        group, _ = window.get_view_index(view)
        if window.active_view_in_group(group) != view:
            window_active_view = window.active_view()
            window.focus_view(view)
            window.focus_view(window_active_view)

import sublime
import sublime_plugin

import os
import re
import sys
import time
import threading
import logging


from .ptty import TerminalPtyProcess, TerminalScreen, TerminalStream
from .ptty import segment_buffer_line
from .key import get_key_code
from .utils import rev_wcwidth, responsive, intermission, settings_on_change


logger = logging.getLogger('Terminus')


def view_size(view):
    pixel_width, pixel_height = view.viewport_extent()
    pixel_per_line = view.line_height()
    pixel_per_char = view.em_width()

    if pixel_per_line == 0 or pixel_per_char == 0:
        return (0, 0)

    nb_columns = int(pixel_width / pixel_per_char) - 3
    if nb_columns < 1:
        nb_columns = 1

    nb_rows = int(pixel_height / pixel_per_line)
    if nb_rows < 1:
        nb_rows = 1

    return (nb_rows, nb_columns)


class Terminal():
    _terminals = {}

    def __init__(self, view):
        self.view = view
        self._terminals[view.id()] = self
        self._cached_cursor = [0, 0]
        self._cached_cursor_is_hidden = [True]

    @classmethod
    def from_id(cls, vid):
        if vid not in cls._terminals:
            return None
        return cls._terminals[vid]

    @classmethod
    def from_tag(cls, tag):
        for terminal in cls._terminals.values():
            if terminal.tag == tag:
                return terminal
        return None

    def _need_to_render(self):
        flag = False
        if self.screen.dirty:
            flag = True
        elif self.screen.cursor.x != self._cached_cursor[0] or \
                self.screen.cursor.y != self._cached_cursor[1]:
            flag = True
        elif self.screen.cursor.hidden != self._cached_cursor_is_hidden[0]:
            flag = True

        if flag:
            self._cached_cursor[0] = self.screen.cursor.x
            self._cached_cursor[1] = self.screen.cursor.y
            self._cached_cursor_is_hidden[0] = self.screen.cursor.hidden
        return flag

    def _start_rendering(self):
        lock = threading.Lock()
        data = [""]
        end_loop_handled = [False]
        parent_window = self.view.window() or sublime.active_window()

        @responsive(period=1, default=True)
        def view_is_attached():
            if self.panel_name:
                window = self.view.window() or parent_window
                terminus_view = window.find_output_panel(self.panel_name)
                return terminus_view and terminus_view.id() == self.view.id()
            else:
                return self.view.window()

        @responsive(period=1, default=True)
        def process_is_alive():
            return self.process.isalive()

        @responsive(period=1, default=False)
        def was_resized():
            size = view_size(self.view)
            return self.screen.lines != size[0] or self.screen.columns != size[1]

        def cleanup():
            with lock:
                if not end_loop_handled[0]:
                    end_loop_handled[0] = True
                    sublime.set_timeout(lambda: self.cleanup())

        def reader():
            while process_is_alive() and view_is_attached():
                # a trick to make window responsive when there is a lot of printings
                # not sure why it works though
                self.view.window()
                try:
                    temp = self.process.read(1024)
                except EOFError:
                    data[0] = ""
                    break
                with lock:
                    data[0] += temp

            cleanup()

        threading.Thread(target=reader).start()

        def renderer():
            while process_is_alive() and view_is_attached():
                with intermission(period=0.03):
                    with lock:
                        if len(data[0]) > 0:
                            logger.debug("receieved: {}".format(data[0]))
                            self.stream.feed(data[0])
                            data[0] = ""

                    if was_resized():
                        self.handle_resize()

                    if self._need_to_render():
                        self.view.run_command("terminus_render")

            cleanup()

        threading.Thread(target=renderer).start()

    def open(self, cmd, cwd=None, env=None, title=None, offset=0, panel_name=None, tag=None):
        self.panel_name = panel_name
        self.tag = tag
        self.set_title(title)
        self.offset = offset
        _env = os.environ.copy()
        _env.update(env)
        size = view_size(self.view)
        if size == (1, 1):
            size = (24, 80)
        logger.debug("view size: {}".format(str(size)))
        self.process = TerminalPtyProcess.spawn(cmd, cwd=cwd, env=_env, dimensions=size)
        self.screen = TerminalScreen(size[1], size[0], process=self.process, history=10000)
        self.stream = TerminalStream(self.screen)
        self._start_rendering()

    def close(self):
        vid = self.view.id()
        if vid in self._terminals:
            del self._terminals[vid]
        self.process.terminate()

    def cleanup(self):
        # process might be still alive but view was detached
        # make sure the process is terminated
        self.close()

        self.view.run_command(
            "append",
            {"characters": "\nprocess is terminated with return code {}.".format(
                self.process.exitstatus)}),
        self.view.set_read_only(True)

        if self.process.exitstatus == 0:
            if self.panel_name:
                window = self.view.window()
                if window:
                    window.destroy_output_panel(self.panel_name)
            else:
                window = self.view.window()
                if window:
                    window.focus_view(self.view)
                    window.run_command("close")

    def handle_resize(self):
        size = view_size(self.view)
        logger.debug("handle resize {} {} -> {} {}".format(
            self.screen.lines, self.screen.columns, size[0], size[1]))
        self.process.setwinsize(*size)
        self.screen.resize(*size)

    def set_title(self, title):
        self.view.set_name(title)

    def send_key(self, *args, **kwargs):
        kwargs["application_mode"] = self.application_mode_enabled()
        kwargs["new_line_mode"] = self.new_line_mode_enabled()
        self.send_string(get_key_code(*args, **kwargs), normalized=False)

    def send_string(self, string, normalized=True):
        if normalized:
            # normalize CR and CRLF to CR (or CRLF if LNM)
            string = string.replace("\r\n", "\n")
            if self.new_line_mode_enabled():
                string = string.replace("\n", "\r\n")
            else:
                string = string.replace("\n", "\r")

        logger.debug("sent {}".format(string))
        self.process.write(string)

    def bracketed_paste_mode_enabled(self):
        return (2004 << 5) in self.screen.mode

    def new_line_mode_enabled(self):
        return (20 << 5) in self.screen.mode

    def application_mode_enabled(self):
        return (1 << 5) in self.screen.mode

    def __del__(self):
        # make sure the process is terminated
        self.process.terminate(force=True)

        if self.process.isalive():
            logger.debug("process becomes orphaned")
        else:
            logger.debug("process is terminated")


def _get_incremental_key():
    _counter = [0]

    def _():
        _counter[0] += 1
        return "#{}".format(_counter)
    return _


get_incremental_key = _get_incremental_key()


class TerminusRender(sublime_plugin.TextCommand):
    def run(self, edit, force=False):
        self.force = force
        view = self.view
        startt = time.time()
        terminal = Terminal.from_id(view.id())
        if not terminal:
            return

        screen = terminal.screen
        self.update_lines(edit, terminal)
        self.update_cursor(edit, terminal)
        self.trim_trailing_spaces(edit, terminal)
        self.trim_history(edit, terminal)
        logger.debug("updating lines takes {}s".format(str(time.time() - startt)))
        logger.debug("mode: {}, cursor: {}.{}".format(
            [m >> 5 for m in screen.mode], screen.cursor.x, screen.cursor.y))

    def scroll_to_cursor(self, terminal):
        view = self.view
        layout = view.text_to_layout(view.text_point(terminal.offset, 0))
        view.set_viewport_position(layout, True)

    def update_cursor(self, edit, terminal):
        view = self.view

        sel = view.sel()
        sel.clear()

        screen = terminal.screen
        if screen.cursor.hidden:
            return

        cursor = screen.cursor
        offset = terminal.offset

        if not self.force and len(view.sel()) > 0 and view.sel()[0].empty():
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
        self.scroll_to_cursor(terminal)

    def update_lines(self, edit, terminal):
        # cursor = screen.cursor
        screen = terminal.screen
        dirty_lines = screen.dirty.copy()
        if dirty_lines:
            # replay history
            history = screen.history
            terminal.offset += len(history)
            offset = terminal.offset
            logger.debug("add {} line(s) to scroll back history".format(len(history)))

            for line in range(len(history)):
                buffer_line = history.pop()
                self.update_line(edit, offset - line - 1, buffer_line)

            # update dirty line¡s
            logger.debug("screen is dirty: {}".format(str(dirty_lines)))
            screen.dirty.clear()
            for line in dirty_lines:
                buffer_line = screen.buffer[line]
                self.update_line(edit, line + offset, buffer_line)

    def update_line(self, edit, line, buffer_line):
        view = self.view
        # make sure the view has enough lines
        self.ensure_position(edit, line)
        line_region = view.line(view.text_point(line, 0))
        segments = list(segment_buffer_line(buffer_line))
        view.erase(edit, line_region)
        view.insert(edit, line_region.begin(), "".join(s[0] for s in segments).rstrip())
        self.colorize_line(edit, line, segments)

    def colorize_line(self, edit, line, segments):
        view = self.view
        for s in segments:
            fg, bg = s[3:]
            if fg != "default" or bg != "default":
                self.ensure_position(edit, line, s[2])
                a = view.text_point(line, s[1])
                b = view.text_point(line, s[2])
                view.add_regions(
                    get_incremental_key(),
                    [sublime.Region(a, b)],
                    "terminus.{}.{}".format(fg, bg))

    def ensure_position(self, edit, row, col=0):
        view = self.view
        lastrow = view.rowcol(view.size())[0]
        if lastrow < row:
            view.insert(edit, view.size(), "\n" * (row - lastrow))
        line_region = view.line(view.text_point(row, 0))
        lastcol = view.rowcol(line_region.end())[1]
        if lastcol < col:
            view.insert(edit, line_region.end(), " " * (col - lastcol))

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
            if len(text.strip()) == 0:
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

    def trim_history(self, edit, terminal, n=10000, m=1000):
        """
        If number of lines in view > n, remove m lines from the top
        """
        view = self.view
        screen = terminal.screen
        lastrow = view.rowcol(view.size())[0]
        if lastrow + 1 > n:
            m = max(lastrow + 1 - n, m)
            logger.debug("removing {} lines from the top".format(m))
            top_region = sublime.Region(0, view.line(view.text_point(m - 1, 0)).end() + 1)
            view.erase(edit, top_region)
            terminal.offset -= m
            lastrow -= m

        if lastrow > terminal.offset + screen.lines:
            tail_region = sublime.Region(
                view.text_point(terminal.offset + screen.lines, 0),
                view.size()
            )
            view.erase(edit, tail_region)


class TerminusOpen(sublime_plugin.WindowCommand):

    def run(
            self,
            config_name=None,
            cmd=None,
            cwd=None,
            env={},
            title=None,
            panel_name=None,
            tag=None):
        config = None

        if config_name:
            config = self.get_config_by_name(config_name)
        elif cmd:
            config = {
                "name": "Terminus",
                "cmd": cmd,
                "env": env,
                "title": title
            }
        else:
            self.show_configs()
            return

        cmd = config["cmd"]

        if "env" in config:
            _env = config["env"]
        else:
            _env = {}

        if sys.platform.startswith("win"):
            pass

        else:
            if "TERM" not in _env:
                settings = sublime.load_settings("Terminus.sublime-settings")
                _env["TERM"] = settings.get("unix_term", "linux")

            if _env["TERM"] not in ["linux", "xterm", "xterm-16color", "xterm-256color"]:
                raise Exception("{} is not supported.".format(_env["TERM"]))

            if "LANG" not in _env:
                if "LANG" in os.environ:
                    _env["LANG"] = os.environ["LANG"]
                else:
                    _env["LANG"] = "en_US.UTF-8"

        _env.update(env)

        if cwd:
            pass
        else:
            if self.window.folders():
                cwd = self.window.folders()[0]
            else:
                cwd = os.path.expanduser("~")

        if not title:
            title = config["name"]

        if panel_name:
            self.window.destroy_output_panel(panel_name)  # do not reuse
            terminus_view = self.window.get_output_panel(panel_name)
        else:
            terminus_view = self.window.new_file()

        terminus_view.run_command(
            "terminus_activate",
            {
                "cmd": cmd,
                "cwd": cwd,
                "env": _env,
                "title": title,
                "panel_name": panel_name,
                "tag": tag
            })

        if panel_name:
            self.window.run_command("show_panel", {"panel": "output.{}".format(panel_name)})
            self.window.focus_view(terminus_view)

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


class TerminusActivate(sublime_plugin.TextCommand):

    def run(self, _, **kwargs):
        terminus_settings = sublime.load_settings("Terminus.sublime-settings")

        view = self.view
        view_settings = view.settings()
        view_settings.set("terminus_view", True)
        if "panel_name" in kwargs:
            view_settings.set("terminus_view.panel_name", kwargs["panel_name"])
        if "tag" in kwargs:
            view_settings.set("terminus_view.tag", kwargs["tag"])
        view_settings.set("terminus_view.args", kwargs)
        view_settings.set(
            "terminus_view.natural_keyboard",
            terminus_settings.get("natural_keyboard", True))
        view.set_scratch(True)
        view.set_read_only(False)
        view_settings.set("gutter", False)
        view_settings.set("highlight_line", False)
        view_settings.set("auto_complete_commit_on_tab", False)
        view_settings.set("draw_centered", False)
        view_settings.set("word_wrap", False)
        view_settings.set("auto_complete", False)
        view_settings.set("draw_white_space", "none")
        view_settings.set("draw_indent_guides", False)
        view_settings.set("caret_style", "blink")
        view_settings.set("scroll_past_end", True)
        view_settings.set("color_scheme", "Terminus.sublime-color-scheme")
        # disable vintageous
        view_settings.set("__vi_external_disable", True)
        for key, value in terminus_settings.get("view_settings", {}).items():
            view_settings.set(key, value)

        if view.size() > 0:
            kwargs["offset"] = view.rowcol(view.size())[0] + 2
            logger.debug("activating with offset %s", kwargs["offset"])

        terminal = Terminal(self.view)
        terminal.open(**kwargs)


class TerminusEventHandler(sublime_plugin.EventListener):

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
        if command == "terminus_render":
            return
        elif command == "insert" and "characters" in args:
            chars = args["characters"]
            logger.debug("char {} detected".format(chars))
            terminal.send_string(chars)
        elif command:
            logger.debug("undo {}".format(command))
            view.run_command("soft_undo")

    def on_text_command(self, view, name, args):
        if not view.settings().get('terminus_view'):
            return

        if name == "paste":
            return ("terminus_paste", None)
        elif name == "paste_from_history":
            return ("terminus_paste_from_history", None)

    def on_post_text_command(self, view, name, args):
        """
        help panel terminal to capture copied text
        """
        if not view.settings().get('terminus_view'):
            return

        if name == 'copy' or name == 'terminus_copy':
            if not view.settings().get('is_widget'):
                return
            self.g_clipboard_history.push_text(sublime.get_clipboard())

    def on_activated(self, view):
        terminal = Terminal.from_id(view.id())
        if terminal:
            # TODO: update cursor
            # sublime.set_timeout(
            #     lambda: view.run_command("terminus_render", {"force": True}), 100)
            return

        settings = view.settings()
        if not settings.has("terminus_view.args"):
            return

        kwargs = settings.get("terminus_view.args")
        if "cmd" not in kwargs:
            return

        sublime.set_timeout(lambda: view.run_command("terminus_activate", kwargs), 100)


class TerminusClose(sublime_plugin.TextCommand):

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


class TerminusKeypress(sublime_plugin.TextCommand):

    def run(self, _, **kwargs):
        terminal = Terminal.from_id(self.view.id())
        if not terminal or not terminal.process.isalive():
            return
        terminal.send_key(**kwargs)
        self.view.run_command("terminus_render")


class TerminusCopy(sublime_plugin.TextCommand):
    """
    It does nothing special now, just `copy`.
    """
    def run(self, edit):
        view = self.view
        if not view.settings().get("terminus_view"):
            return
        view.run_command("copy")


class TerminusPaste(sublime_plugin.TextCommand):

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


class TerminusDeleteWord(sublime_plugin.TextCommand):
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


class ToggleTerminusPanel(sublime_plugin.WindowCommand):

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


class TerminusSendString(sublime_plugin.WindowCommand):
    """
    Send string to a (tagged) terminal
    """

    def run(self, string, tag=None):
        if tag:
            terminal = Terminal.from_tag(tag)
            if terminal:
                self.bring_view_to_topmost(terminal.view)
        else:
            view = self.get_terminus_panel()
            terminal = None
            if view:
                self.window.run_command("show_panel", {"panel": "output.{}".format(
                    view.settings().get("terminus_view.panel_name")
                )})
                terminal = Terminal.from_id(view.id())
            else:
                view = self.get_terminus_view()
                if view:
                    self.bring_view_to_topmost(view)
                    terminal = Terminal.from_id(view.id())

        if not terminal:
            raise Exception("no terminal found")
        elif not terminal.process.isalive():
            raise Exception("process is terminated")

        terminal.send_string(string)
        terminal.view.run_command("terminus_render")

    def get_terminus_panel(self):
        window = self.window
        for panel in window.panels():
            panel_view = window.find_output_panel(panel.replace("output.", ""))
            if panel_view:
                terminal = Terminal.from_id(panel_view.id())
                if terminal:
                    return panel_view
        return None

    def get_terminus_view(self):
        window = self.window
        for v in window.views():
            terminal = Terminal.from_id(v.id())
            if terminal:
                return v

    def bring_view_to_topmost(self, view):
        # move the view to the top of the group
        window = view.window()
        group, index = window.get_view_index(view)
        group_active_view = window.active_view_in_group(group)
        if group_active_view != view:
            window_active_view = window.active_view()
            window.focus_view(view)
            window.focus_view(window_active_view)


def plugin_loaded():
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

import sublime
import sublime_plugin

import os
import sys
import time
import threading
import logging
from functools import wraps
from copy import deepcopy
from contextlib import contextmanager
from collections import defaultdict, deque

import pyte
from pyte.screens import StaticDefaultDict, History, Cursor, Margins
from wcwidth import wcwidth

from .key import get_key_code
from .utils import settings_on_change


if sys.platform.startswith("win"):
    from winpty import PtyProcess
else:
    from ptyprocess import PtyProcess


logger = logging.getLogger('Console')

if not logger.hasHandlers():
    ch = logging.StreamHandler(sys.stdout)
    logger.addHandler(ch)


def which_char(text, cursor_position):
    w = 0
    i = 0
    # loop over to check for double width chars
    for i, c in enumerate(text):
        w += wcwidth(c)
        if w >= cursor_position:
            break
    return i


def segment_buffer_line(buffer_line):
    """
    segment a buffer line based on bg and fg colors
    """
    is_wide_char = False
    text = ""
    start = 0
    counter = 0
    fg = "default"
    bg = "default"

    if buffer_line:
        last_index = max(buffer_line.keys()) + 1
    else:
        last_index = 0

    for i in range(last_index):
        if is_wide_char:
            is_wide_char = False
            continue
        char = buffer_line[i]
        is_wide_char = wcwidth(char.data) == 2

        if counter == 0:
            counter = i
            text = " " * i

        if fg != char.fg or bg != char.bg:
            yield text, start, counter, fg, bg
            fg = char.fg
            bg = char.bg
            text = char.data
            start = counter
        else:
            text += char.data

        counter += 1

    yield text, start, counter, fg, bg


def responsive(period=0.1, default=True):
    """
    make a condition checker more responsive
    """
    def wrapper(f):
        t = [0]

        @wraps(f)
        def _(*args, **kwargs):
            now = time.time()
            if now - t[0] > period:
                t[0] = now
                return f(*args, **kwargs)
            else:
                return default

        return _

    return wrapper


@contextmanager
def intermission(period=0.1):
    """
    intermission of period seconds.
    """
    startt = time.time()
    yield
    deltat = time.time() - startt
    if deltat < period:
        time.sleep(period - deltat)


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


class ConsolePtyProcess(PtyProcess):

    if sys.platform.startswith("win"):
        def read(self, nbytes):
            return super(ConsolePtyProcess, self).read(nbytes).encode("utf-8")

        def write(self, data):
            super(ConsolePtyProcess, self).write(data.decode("utf-8"))
    else:
        def read(self, nbytes):
            return super(ConsolePtyProcess, self).read(nbytes)

        def write(self, data):
            super(ConsolePtyProcess, self).write(data)


class ConsoleScreen(pyte.HistoryScreen):
    offset = 0
    _alt_screen_mode = False
    _primary_buffer = {}

    def __init__(self, *args, **kwargs):
        if "process" in kwargs:
            self._process = kwargs["process"]
            del kwargs["process"]
        else:
            raise Exception("missing process")
        super(ConsoleScreen, self).__init__(*args, **kwargs)

    def write_process_input(self, data):
        self._process.write(data.encode("utf-8"))

    def set_margins(self, top=None, bottom=None):
        if (top is None or top == 0) and bottom is None:
            # https://github.com/selectel/pyte/commit/676610b43954b644c05823371df6daf87caafdad
            self.margins = None
        else:
            super().set_margins(top, bottom)

    def set_mode(self, *modes, **kwargs):
        super().set_mode(*modes, **kwargs)
        if 1049 << 5 in self.mode and not self._alt_screen_mode:
            self._alt_screen_mode = True
            self.switch_to_screen(alt=True)

    def reset_mode(self, *modes, **kwargs):
        super().reset_mode(*modes, **kwargs)
        if 1049 << 5 not in self.mode and self._alt_screen_mode:
            self._alt_screen_mode = False
            self.switch_to_screen(alt=False)

    def switch_to_screen(self, alt=False):
        if alt:
            self._primary_buffer["buffer"] = self.buffer
            self._primary_buffer["history"] = self.history
            self._primary_buffer["cursor"] = self.cursor
            self.buffer = defaultdict(lambda: StaticDefaultDict(self.default_char))
            self.history = History(deque(maxlen=0), deque(maxlen=0), 0.5, 0, 0)
            self.cursor = Cursor(0, 0)
        else:
            self.buffer = self._primary_buffer["buffer"]
            self.history = self._primary_buffer["history"]
            self.cursor = self._primary_buffer["cursor"]

        self.dirty.update(range(self.lines))

    def alt_screen_mode(self):
        return self._alt_screen_mode

    def index(self):
        if not self.alt_screen_mode() and self.cursor.y == self.lines - 1:
            self.offset += 1
        super().index()

    def erase_in_display(self, how=0):
        # dump the screen to history
        logger.debug("erase_in_display: %s", how)
        if not self.alt_screen_mode() and \
                (how == 2 or (how == 0 and self.cursor.x == 0 and self.cursor.y == 0)):
            self.scroll_screen_into_history()

        super().erase_in_display(how)

    def scroll_screen_into_history(self):
        # find the first non-empty line from the botton
        found = -1
        for nz_line in reversed(range(self.lines)):
            text = "".join([c.data for c in self.buffer[nz_line].values()])
            if len(text.strip()) > 0:
                found = nz_line
                break
        self.history.top.extend(deepcopy(self.buffer[y]) for y in range(found + 1))
        self.offset += found + 1

    def scroll_up(self, n):
        logger.debug("scroll_up {}".format(n))
        top, bottom = self.margins or Margins(0, self.lines - 1)
        for y in range(top, bottom + 1):
            if y + n > bottom:
                for j in range(self.columns):
                    self.buffer[y][j] = self.cursor.attrs
            else:
                self.buffer[y] = deepcopy(self.buffer[y+n])
        self.dirty.update(range(self.lines))

    def scroll_down(self, n):
        logger.debug("scoll_down {}".format(n))
        top, bottom = self.margins or Margins(0, self.lines - 1)
        for y in reversed(range(top, bottom + 1)):
            if y - n < top:
                for j in range(self.columns):
                    self.buffer[y][j] = self.cursor.attrs
            else:
                self.buffer[y] = deepcopy(self.buffer[y-n])
        self.dirty.update(range(self.lines))


class ConsoleByteStream(pyte.ByteStream):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.csi["S"] = "scroll_up"
        self.csi["T"] = "scroll_down"


class Console():
    _consoles = {}
    _cached_cursor = [0, 0]
    _cached_cursor_is_hidden = [True]

    def __init__(self, view):
        self._consoles[view.id()] = self
        self.view = view
        self.view.set_scratch(True)
        # self.view.set_read_only(True)
        self.view.settings().set("gutter", False)
        self.view.settings().set("highlight_line", False)
        self.view.settings().set("auto_complete_commit_on_tab", False)
        self.view.settings().set("draw_centered", False)
        self.view.settings().set("word_wrap", True)
        self.view.settings().set("auto_complete", False)
        self.view.settings().set("draw_white_space", "none")
        self.view.settings().set("draw_indent_guides", False)
        self.view.settings().set("caret_style", "blink")
        self.view.settings().set("scroll_past_end", True)
        self.view.settings().set("color_scheme", "Console.sublime-color-scheme")

    @classmethod
    def from_id(cls, vid):
        if vid not in cls._consoles:
            return None
        return cls._consoles[vid]

    @responsive(period=1, default=False)
    def _was_resized(self):
        size = view_size(self.view)
        return self.screen.lines != size[0] or self.screen.columns != size[1]

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
        data = [b""]

        view_is_attached = responsive(period=0.001, default=True)(self.view.window)
        console_is_alive = responsive(period=1, default=True)(
            lambda: self.process.isalive() and view_is_attached())

        def reader():
            # run self.view.windows() via `view_is_attached` periodically to refresh gui
            while console_is_alive() and view_is_attached():
                try:
                    temp = self.process.read(1024)
                except EOFError:
                    data[0] = b""
                    break
                with lock:
                    data[0] += temp

        threading.Thread(target=reader).start()

        def renderer():
            while console_is_alive():
                with intermission(period=0.03):
                    with lock:
                        if len(data[0]) > 0:
                            logger.debug("receieved: {}".format(data[0]))
                            self.stream.feed(data[0])
                            data[0] = b""

                    if self._was_resized():
                        self.handle_resize()

                    if self._need_to_render():
                        self.view.run_command("console_render")

            sublime.set_timeout(lambda: self.handle_process_termination())

        threading.Thread(target=renderer).start()

    def open(self, cmd, cwd=None, env=None, title=None):
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self.title = title
        self.set_title(title)

        _env = os.environ.copy()
        _env.update(env)
        size = view_size(self.view)
        logger.debug("view size: {}".format(str(size)))

        self.process = ConsolePtyProcess.spawn(self.cmd, cwd=cwd, env=_env, dimensions=size)
        self.screen = ConsoleScreen(size[1], size[0], process=self.process, history=10000)
        self.stream = ConsoleByteStream(self.screen)
        self._start_rendering()

    def close(self):
        vid = self.view.id()
        if vid in self._consoles:
            del self._consoles[vid]
        self.process.terminate()

    def handle_process_termination(self):
        # process ended
        if self.process.exitstatus == 0:
            window = self.view.window()
            if window:
                window.focus_view(self.view)
                window.run_command("close")
        else:
            self.view.run_command(
                "append",
                {"characters": "\nprocess terminated with return code {}.".format(
                    self.process.exitstatus
                 )}),
            self.view.set_read_only(True)

    def handle_resize(self):
        size = view_size(self.view)
        logger.debug("handle resize {} {} -> {} {}".format(
            self.screen.lines, self.screen.columns, size[0], size[1]))
        self.process.setwinsize(*size)
        self.screen.resize(*size)

    def set_title(self, title):
        self.view.set_name(title)

    def send_key(self, *args, **kwargs):
        self.send_string(get_key_code(*args, **kwargs))

    def send_string(self, string):
        logger.debug("sent {}".format(string))
        self.process.write(string.encode("utf-8"))

    def bracketed_paste_mode_enabled(self):
        return (2004 << 5) in self.screen.mode

    def __del__(self):
        # make sure the process is terminated
        self.process.terminate(force=True)

        if self.process.isalive():
            logger.debug("process becomes orphaned")
        else:
            logger.debug("process has terminated")


def _get_incremental_key():
    _counter = [0]

    def _():
        _counter[0] += 1
        return "#{}".format(_counter)
    return _


get_incremental_key = _get_incremental_key()


class ConsoleRender(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        startt = time.time()
        console = Console.from_id(view.id())
        if not console:
            return

        screen = console.screen
        self.update_lines(edit, screen)
        self.update_cursor(edit, screen)
        self.show_offset_at_top(screen)
        self.trim_trailing_spaces(edit, screen)
        self.trim_history(edit, screen)
        logger.debug("updating lines takes {}s".format(str(time.time() - startt)))
        logger.debug("mode: {}".format([m >> 5 for m in screen.mode]))

    def show_offset_at_top(self, screen):
        view = self.view
        layout = view.text_to_layout(view.text_point(screen.offset, 0))
        view.set_viewport_position(layout, False)

    def update_cursor(self, edit, screen):
        view = self.view
        cursor = screen.cursor
        offset = screen.offset
        # make sure the view has enough lines
        self.ensure_position(edit, cursor.y + offset)

        line_region = view.line(view.text_point(cursor.y + offset, 0))
        text = view.substr(line_region)

        pt = view.text_point(cursor.y + offset, which_char(text, cursor.x) + 1)
        if view.rowcol(pt)[0] > cursor.y + offset:
            # it may happen if the line is empty
            pt = pt - 1
        sel = view.sel()
        sel.clear()
        if not screen.cursor.hidden:
            sel.add(sublime.Region(pt, pt))

    def update_lines(self, edit, screen):
        # cursor = screen.cursor
        offset = screen.offset
        dirty_lines = screen.dirty.copy()
        if dirty_lines:
            # replay history
            top = screen.history.top
            for line in range(len(top)):
                buffer_line = top.pop()
                self.update_line(edit, offset - line - 1, buffer_line)

            # update dirty lines
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
        view.insert(edit, line_region.begin(), "".join(s[0] for s in segments))
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
                    "console.{}.{}".format(fg, bg))

    def ensure_position(self, edit, row, col=0):
        view = self.view
        lastrow = view.rowcol(view.size())[0]
        if lastrow < row:
            view.insert(edit, view.size(), "\n" * (row - lastrow))
        line_region = view.line(view.text_point(row, 0))
        lastcol = view.rowcol(line_region.end())[1]
        if lastcol < col:
            view.insert(edit, line_region.end(), " " * (col - lastcol))

    def trim_trailing_spaces(self, edit, screen):
        view = self.view
        cursor = screen.cursor
        cursorrow = screen.offset + screen.cursor.y
        lastrow = view.rowcol(view.size())[0]
        row = lastrow
        while row > cursorrow:
            line_region = view.line(view.text_point(row, 0))
            text = view.substr(line_region)
            if len(text.strip()) == 0:
                region = view.line(view.text_point(row, 0))
                view.erase(edit, sublime.Region(region.begin() - 1, region.end()))
                row = row - 1
            else:
                break
        if row == cursorrow:
            line_region = view.line(view.text_point(row, 0))
            text = view.substr(line_region)
            trailing_region = sublime.Region(
                line_region.begin() + which_char(text, cursor.x) + 1,
                line_region.end())
            if not trailing_region.empty() and len(view.substr(trailing_region).strip()) == 0:
                view.erase(edit, trailing_region)

    def trim_history(self, edit, screen, n=10000, m=1000):
        """
        If number of lines in view > n, remove m lines from the top
        """
        view = self.view
        lastrow = view.rowcol(view.size())[0]
        if lastrow + 1 > n:
            m = max(lastrow + 1 - n, m)
            logger.debug("removing {} lines from the top".format(m))
            top_region = sublime.Region(0, view.line(view.text_point(m - 1, 0)).end() + 1)
            view.erase(edit, top_region)
            screen.offset -= m
            lastrow -= m

        if lastrow > screen.offset + screen.lines:
            tail_region = sublime.Region(
                view.text_point(screen.offset + screen.lines, 0),
                view.size()
            )
            view.erase(edit, tail_region)


class ConsoleKeypress(sublime_plugin.TextCommand):

    def run(self, _, **kwargs):
        console = Console.from_id(self.view.id())
        if not console or not console.process.isalive():
            return
        console.send_key(**kwargs)
        self.view.run_command("console_render")


class ConsoleSendString(sublime_plugin.TextCommand):

    def run(self, _, string):
        console = Console.from_id(self.view.id())
        if not console or not console.process.isalive():
            return
        console.send_string(string)
        self.view.run_command("console_render")


class ConsolePaste(sublime_plugin.TextCommand):

    def run(self, edit, bracketed=False):
        view = self.view
        console = Console.from_id(view.id())
        if not console:
            return

        bracketed = bracketed or console.bracketed_paste_mode_enabled()
        if bracketed:
            console.send_key("bracketed_paste_mode_start")

        copied = sublime.get_clipboard()
        for char in copied:
            console.send_string(char)

        if bracketed:
            console.send_key("bracketed_paste_mode_end")


class ConsoleEventHandler(sublime_plugin.ViewEventListener):

    @classmethod
    def is_applicable(cls, settings):
        return settings.get("console_view", False)

    def on_pre_close(self):
        view = self.view
        console = Console.from_id(view.id())
        if console:
            console.close()

    def on_modified(self):
        # to catch unicode input
        view = self.view
        console = Console.from_id(view.id())
        if not console or not console.process.isalive():
            return
        command, args, _ = view.command_history(0)
        if command == "console_render":
            return
        elif command == "insert" and "characters" in args:
            chars = args["characters"]
            logger.debug("char {} detected".format(chars))
            console = Console.from_id(view.id())
            if console:
                console.send_string(chars)
        else:
            logger.debug("undo {}".format(command))
            view.run_command("soft_undo")


class ConsoleOpen(sublime_plugin.WindowCommand):

    def run(self, cmd=None, cwd=None, env={}, title="Console"):
        if not cmd:
            if sys.platform.startswith("win"):
                cmd = "C:\\Windows\\System32\\cmd.exe"
            else:
                if "SHELL" in os.environ:
                    cmd = [os.environ["SHELL"], "-i", "-l"]
                else:
                    cmd = ["/bin/bash", "-i", "-l"]

        settings = sublime.load_settings("Console.sublime-settings")

        if sys.platform.startswith("win"):
            _env = {}
            _env.update(env)
        else:
            _env = {
                "TERM": settings.get("unix_term", "linux"),
                "LANG": "en_US.UTF-8"
            }
            _env.update(env)

        if not cwd:
            if self.window.folders():
                cwd = self.window.folders()[0]

        self.window.new_file().run_command(
            "console_activate",
            {
                "cmd": cmd,
                "cwd": cwd,
                "env": _env,
                "title": title
            })


class ConsoleActivate(sublime_plugin.TextCommand):

    def run(self, _, **kwargs):
        self.view.settings().set("console_view", True)
        sublime.set_timeout_async(lambda: self.run_async(**kwargs))

    def run_async(self, **kwargs):
        console = Console(self.view)
        console.open(**kwargs)


def plugin_loaded():
    settings = sublime.load_settings("Console.sublime-settings")

    def on_change(debug):
        if debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.WARNING)

    on_change(settings.get("debug", False))
    settings_on_change(settings, "debug")(on_change)

import sublime
import sublime_plugin

import os
import sys
import time
import threading
import logging

import pyte
from wcwidth import wcwidth

from .key import get_key_code

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


def render_line(buffer_line):
    is_wide_char = False
    text = ""
    for i in buffer_line:
        if is_wide_char:
            is_wide_char = False
            continue
        data = buffer_line[i].data
        is_wide_char = wcwidth(data) == 2
        text += data
    return text


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
    for i in buffer_line:
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


class ConsolePtyProcess(PtyProcess):

    def read(self, nbytes):
        if sys.platform.startswith("win"):
            return super(ConsolePtyProcess, self).read(nbytes).encode("utf-8")
        else:
            return super(ConsolePtyProcess, self).read(nbytes)

    def write(self, data):
        if sys.platform.startswith("win"):
            super(ConsolePtyProcess, self).write(data.decode("utf-8"))
        else:
            super(ConsolePtyProcess, self).write(data)


class ConsoleScreen(pyte.HistoryScreen):
    offset = 0

    def __init__(self, *args, **kwargs):
        if "process" in kwargs:
            self._process = kwargs["process"]
            del kwargs["process"]
        else:
            raise Exception("missing process")
        super(ConsoleScreen, self).__init__(*args, **kwargs)

    def write_process_input(self, data):
        self._process.write(data.encode("utf-8"))

    def index(self):
        if self.cursor.y == self.lines - 1:
            self.offset += 1
        super().index()

    def erase_in_display(self, how=0):
        # dump to screen to history
        if (how == 0 and self.cursor.x == 0 and self.cursor.y == 0) or how == 2:
            # find the first non-empty line from the botton
            found = -1
            for nz_line in reversed(range(self.lines)):
                text = render_line(self.buffer[nz_line])
                if len(text.strip()) > 0:
                    found = nz_line
                    break
            self.history.top.extend(self.buffer[y].copy() for y in range(found + 1))
            self.offset += found + 1

        super().erase_in_display(how)


class ConsoleByteStream(pyte.ByteStream):

    pass


class Console():
    _consoles = {}
    _cached_cursor = [0, 0]
    _cached_cursor_is_hidden = [True]
    _cached_size = [0, 0]

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

    def open(self, cmd, cwd=None, env=None, title=None):
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self.title = title
        self.set_title(title)

        _env = os.environ.copy()
        _env.update(env)
        size = self.view_size()
        self._cached_size[0] = size[0]
        self._cached_size[1] = size[1]
        logger.debug("view size: {}".format(str(size)))

        self.process = ConsolePtyProcess.spawn(self.cmd, cwd=cwd, env=_env, dimensions=size)
        self.screen = ConsoleScreen(size[1], size[0], process=self.process, history=10000)
        self.alt_screen = ConsoleScreen(size[1], size[0], process=self.process, history=10000)
        self.stream = ConsoleByteStream(self.screen)
        self._start_rendering()

    def view_size(self):
        view = self.view
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

    def _have_resized(self):
        size = self.view_size()
        return self._cached_size[0] != size[0] or self._cached_size[1] != size[1]

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

        def reader():
            while self.process.isalive() and self.view.window():
                try:
                    temp = self.process.read(1024)
                except EOFError:
                    data[0] = b""
                    break
                with lock:
                    data[0] += temp
        threading.Thread(target=reader).start()

        def renderer():
            while self.process.isalive() and self.view.window():
                startt = time.time()
                with lock:
                    if len(data[0]) > 0:
                        logger.debug("receieved: {}".format(data[0]))
                        self.stream.feed(data[0])
                        data[0] = b""
                if self._have_resized():
                    self.handle_resize()
                if self._need_to_render():
                    self.view.run_command("console_render")
                deltat = time.time() - startt
                if deltat < 0.02:
                    time.sleep(0.02 - deltat)
        threading.Thread(target=renderer).start()

    def close(self):
        vid = self.view.id()
        if vid in self._consoles:
            del self._consoles[vid]
        self.process.terminate()

    def handle_resize(self):
        size = self.view_size()
        logger.debug("handle resize {} {} -> {} {}".format(
            self._cached_size[0], self._cached_size[1], size[0], size[1]))
        self._cached_size[0] = size[0]
        self._cached_size[1] = size[1]
        self.process.setwinsize(*size)
        self.screen.resize(*size)

    def set_title(self, title):
        self.view.set_name(title)

    def send_key(self, **kwargs):
        self.send_string(get_key_code(**kwargs))

    def send_string(self, string):
        logger.debug("sent {}".format(string))
        self.process.write(string.encode("utf-8"))

    def bracketed_paste_mode_enabled(self):
        return (2004 << 5) in self.screen.mode

    def __del__(self):
        # make sure the process is terminated
        self.process.terminate(force=True)


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


class ConsoleKeypress(sublime_plugin.TextCommand):

    def run(self, _, **kwargs):
        console = Console.from_id(self.view.id())
        console.send_key(**kwargs)
        self.view.run_command("console_render")


class ConsoleSendString(sublime_plugin.TextCommand):

    def run(self, _, string):
        console = Console.from_id(self.view.id())
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
            console.send_string("\x1b[200~")

        copied = sublime.get_clipboard()
        for char in copied:
            console.send_string(char)

        if bracketed:
            console.send_string("\x1b[201~")


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
        command, args, _ = view.command_history(0)
        if command == "console_render":
            return
        elif command == "insert" and "characters" in args:
            chars = args["characters"]
            logger.debug("char {} detecated".format(chars))
            console = Console.from_id(view.id())
            if console:
                console.send_string(chars)
        else:
            logger.debug("undo {}".format(command))
            view.run_command("soft_undo")


class ConsoleOpen(sublime_plugin.WindowCommand):

    def run(self, cmd=None, cwd=None, env=None, title="Console"):
        if not cmd:
            if sys.platform.startswith("win"):
                cmd = "C:\\Windows\\System32\\cmd.exe"
            else:
                if "SHELL" in os.environ:
                    cmd = [os.environ["SHELL"], "-i", "-l"]
                else:
                    cmd = ["/bin/bash", "-i", "-l"]

        if not env:
            if sys.platform.startswith("win"):
                env = {}
            else:
                env = {"TERM": "linux", "LANG": "en_US.UTF-8"}

        if not cwd:
            if self.window.folders():
                cwd = self.window.folders()[0]

        self.window.new_file().run_command(
            "console_activate",
            {
                "cmd": cmd,
                "cwd": cwd,
                "env": env,
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
    if settings.get("debug", False):
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.WARNING)

    _cached = {"debug": settings.get("debug", False)}

    def on_change():
        debug = settings.get("debug", False)
        if debug != _cached["debug"]:
            if debug:
                logger.setLevel(logging.DEBUG)
            else:
                logger.setLevel(logging.WARNING)
            _cached["debug"] = debug

    settings.clear_on_change("debug")
    settings.add_on_change("debug", on_change)

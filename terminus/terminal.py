import sublime

import os
import logging
import threading

from .ptty import TerminalPtyProcess, TerminalScreen, TerminalStream
from .utils import responsive, intermission
from .key import get_key_code


CONTINUATION = "\u200b\u200c\u200b"

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


class Terminal:
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
        done = [False]
        parent_window = self.view.window() or sublime.active_window()

        @responsive(period=1, default=True)
        def view_is_attached():
            if self.panel_name:
                window = self.view.window() or parent_window
                terminus_view = window.find_output_panel(self.panel_name)
                return terminus_view and terminus_view.id() == self.view.id()
            else:
                return self.view.window()

        @responsive(period=1, default=False)
        def was_resized():
            size = view_size(self.view)
            return self.screen.lines != size[0] or self.screen.columns != size[1]

        def feed_data():
            with lock:
                if len(data[0]) > 0:
                    logger.debug("receieved: {}".format(data[0]))
                    self.stream.feed(data[0])
                    data[0] = ""

        def reader():
            while True:
                # a trick to make window responsive when there is a lot of printings
                # not sure why it works though
                self.view.window()
                try:
                    temp = self.process.read(1024)
                except EOFError:
                    break
                with lock:
                    data[0] += temp

                if done[0] or not view_is_attached():
                    break

            done[0] = True

        threading.Thread(target=reader).start()

        def renderer():
            while True:
                with intermission(period=0.03):
                    feed_data()

                    if was_resized():
                        self.handle_resize()

                    if self._need_to_render():
                        self.view.run_command("terminus_render")

                    if done[0] or not view_is_attached():
                        break

            feed_data()
            done[0] = True
            sublime.set_timeout(lambda: self.cleanup())

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
        # self.view.settings().set("wrap_width", size[1])
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
        self.view.run_command("terminus_render")

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
        # self.view.settings().set("wrap_width", size[1])

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

import sublime

import os
import time
import base64
import logging
import tempfile
import threading
from queue import Queue, Empty

from .ptty import TerminalPtyProcess, TerminalScreen, TerminalStream
from .utils import responsive, intermission
from .view import panel_window, view_size
from .key import get_key_code
from .image import get_image_info, image_resize


CONTINUATION = "\u200b\u200c\u200b"

IMAGE = """
<style>
body {{
    margin: 1px;
}}
</style>
<img src="data:image/{what};base64,{data}" width="{width}" height="{height}"/>
"""

logger = logging.getLogger('Terminus')


class Terminal:
    _terminals = {}
    _detached_terminals = []

    def __init__(self, view=None):
        self._title = ""
        self.view = view
        self._cached_cursor = [0, 0]
        self._cached_cursor_is_hidden = [True]
        self.image_count = 0
        self.images = {}
        self._strings = Queue()
        self._pending_to_send_string = [False]
        self._pending_to_clear_scrollback = [False]
        self._pending_to_reset = [None]
        self.lock = threading.Lock()

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

    def attach_view(self, view, offset=None):
        with self.lock:
            self.view = view
            self.detached = False
            Terminal._terminals[view.id()] = self
            if self in Terminal._detached_terminals:
                Terminal._detached_terminals.remove(self)
            self.view.settings().erase("terminus_view.detached")
            # allow screen to be rerendered
            self.screen.dirty.update(range(self.screen.lines))
            self.set_offset(offset)

    def detach_view(self):
        with self.lock:
            self.detached = True
            Terminal._detached_terminals.append(self)
            if self.view.id() in Terminal._terminals:
                del Terminal._terminals[self.view.id()]
            self.view.settings().set("terminus_view.detached", True)
            self.view = None

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
        data = [""]
        done = [False]

        @responsive(period=1, default=True)
        def view_is_attached():
            if self.detached:
                # irrelevant if terminal is detached
                return True
            if self.panel_name:
                return panel_window(self.view)
            else:
                return self.view.window()

        @responsive(period=1, default=False)
        def was_resized():
            size = view_size(self.view)
            return self.screen.lines != size[0] or self.screen.columns != size[1]

        def reader():
            while True:
                try:
                    temp = self.process.read(1024)
                except EOFError:
                    break

                with self.lock:
                    data[0] += temp

                    if done[0] or not view_is_attached():
                        logger.debug("reader breaks")
                        break

            done[0] = True

        threading.Thread(target=reader).start()

        def renderer():

            def feed_data():
                if len(data[0]) > 0:
                    logger.debug("receieved: {}".format(data[0]))
                    self.stream.feed(data[0])
                    data[0] = ""

            while True:
                with intermission(period=0.03), self.lock:
                    feed_data()
                    if not self.detached:
                        if was_resized():
                            self.handle_resize()
                            self.view.run_command("terminus_show_cursor")

                        if self._need_to_render():
                            self.view.run_command("terminus_render")
                            self.screen.dirty.clear()

                    if done[0] or not view_is_attached():
                        logger.debug("renderer breaks")
                        break

            feed_data()
            done[0] = True
            sublime.set_timeout(lambda: self.cleanup())

        threading.Thread(target=renderer).start()

    def set_offset(self, offset=None):
        if offset is not None:
            self.offset = offset
        else:
            if self.view and self.view.size() > 0:
                view = self.view
                self.offset = view.rowcol(view.size())[0] + 1
            else:
                self.offset = 0
        logger.debug("activating with offset %s", self.offset)

    def activate(
            self, config_name, cmd, cwd=None, env=None, title=None,
            panel_name=None, tag=None, auto_close=True):

        view = self.view
        if view:
            self.detached = False
            Terminal._terminals[view.id()] = self
        else:
            Terminal._detached_terminals.append(self)
            self.detached = True

        self.config_name = config_name
        self.panel_name = panel_name
        self.tag = tag
        self.auto_close = auto_close
        self.default_title = title

        if view:
            self.title = title
            self.set_offset()

        size = view_size(view or sublime.active_window().active_view())
        if size == (1, 1):
            size = (24, 80)
        logger.debug("view size: {}".format(str(size)))
        _env = os.environ.copy()
        _env.update(env)
        self.process = TerminalPtyProcess.spawn(cmd, cwd=cwd, env=_env, dimensions=size)
        self.screen = TerminalScreen(
            size[1], size[0], process=self.process, history=10000,
            clear_callback=self.clear_callback, reset_callback=self.reset_callback)
        self.stream = TerminalStream(self.screen)

        self.screen.set_show_image_callback(self.show_image)

        self._start_rendering()

    def close(self):
        logger.debug("close")

        vid = self.view.id()
        if vid in self._terminals:
            del self._terminals[vid]
        self.process.terminate()

    def cleanup(self):
        logger.debug("cleanup")
        self.view.run_command("terminus_render")

        # process might be still alive but view was detached
        # make sure the process is terminated
        self.close()

        self.view.run_command(
            "append",
            {"characters": "\nprocess is terminated with return code {}.".format(
                self.process.exitstatus)}),
        self.view.set_read_only(True)

        if self.process.exitstatus == 0 and self.auto_close:
            self.view.run_command("terminus_close")

        # to avoid being reactivated
        self.view.settings().set("terminus_view.closed", True)

    def handle_resize(self):
        size = view_size(self.view)
        logger.debug("handle resize {} {} -> {} {}".format(
            self.screen.lines, self.screen.columns, size[0], size[1]))
        self.process.setwinsize(*size)
        self.screen.resize(*size)

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        if not self.detached:
            value = value if value else self.config_name
            self._title = value
            self.view.set_name(value)

    def clear_callback(self):
        self._pending_to_clear_scrollback[0] = True

    def reset_callback(self):
        if self._pending_to_reset[0] is None:
            self._pending_to_reset[0] = False
        else:
            self._pending_to_reset[0] = True

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

        no_queue = not self._pending_to_send_string[0]
        if no_queue and len(string) <= 512:
            logger.debug("sent: {}".format(string[0:64] if len(string) > 64 else string))
            self.process.write(string)
        else:
            for i in range(0, len(string), 512):
                self._strings.put(string[i:i+512])
            if no_queue:
                self._pending_to_send_string[0] = True
                threading.Thread(target=self.process_send_string).start()

    def process_send_string(self):
        while True:
            try:
                string = self._strings.get(False)
                logger.debug("sent: {}".format(string[0:64] if len(string) > 64 else string))
                self.process.write(string)
            except Empty:
                self._pending_to_send_string[0] = False
                return
            else:
                time.sleep(0.1)

    def bracketed_paste_mode_enabled(self):
        return (2004 << 5) in self.screen.mode

    def new_line_mode_enabled(self):
        return (20 << 5) in self.screen.mode

    def application_mode_enabled(self):
        return (1 << 5) in self.screen.mode

    def find_image(self, pt):
        view = self.view
        for pid in self.images:
            region = view.query_phantom(pid)[0]
            if region.end() == pt:
                return pid
        return None

    def show_image(self, data, args, cr=None):
        view = self.view

        if "inline" not in args or not args["inline"]:
            return

        cursor = self.screen.cursor
        pt = view.text_point(self.offset + cursor.y, cursor.x)

        databytes = base64.decodebytes(data.encode())

        image_info = get_image_info(databytes)
        if not image_info:
            logger.error("cannot get image info")
            return

        what, width, height = image_info

        _, image_path = tempfile.mkstemp(suffix="." + what)
        with open(image_path, "wb") as f:
            f.write(databytes)

        width, height = image_resize(
            width,
            height,
            args["width"] if "width" in args else None,
            args["height"] if "height" in args else None,
            view.em_width(),
            view.viewport_extent()[0] - 3 * view.em_width(),
            args["preserveAspectRatio"] if "preserveAspectRatio" in args else 1
        )

        if self.find_image(pt):
            self.view.run_command("terminus_insert", {"point": pt, "character": " "})
            pt += 1

        self.image_count += 1
        p = view.add_phantom(
            "terminus_image#{}".format(self.image_count),
            sublime.Region(pt, pt),
            IMAGE.format(
                what=what,
                data=data,
                width=width,
                height=height,
                count=self.image_count),
            sublime.LAYOUT_INLINE,
        )
        self.images[p] = image_path

        if cr:
            self.screen.index()

    def clean_images(self):
        view = self.view
        for pid in list(self.images.keys()):
            region = view.query_phantom(pid)[0]
            if region.empty() and region.begin() == 0:
                view.erase_phantom_by_id(pid)
                if pid in self.images:
                    try:
                        os.remove(self.images[pid])
                    except Exception:
                        pass
                    del self.images[pid]

    def __del__(self):
        # make sure the process is terminated
        self.process.terminate(force=True)

        # remove images
        for image_path in list(self.images.values()):
            try:
                os.remove(image_path)
            except Exception:
                pass

        if self.process.isalive():
            logger.debug("process becomes orphaned")
        else:
            logger.debug("process is terminated")

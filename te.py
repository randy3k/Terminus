import sys
import logging
from copy import copy
from collections import defaultdict, deque
from wcwidth import wcwidth

import pyte
from pyte.screens import StaticDefaultDict, History, Cursor, Margins

if sys.platform.startswith("win"):
    from winpty import PtyProcess
else:
    from ptyprocess import PtyProcessUnicode as PtyProcess


logger = logging.getLogger('Terminus')


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


class TerminalPtyProcess(PtyProcess):

    pass


class TerminalScreen(pyte.HistoryScreen):
    offset = 0
    _alt_screen_mode = False

    def __init__(self, *args, **kwargs):
        if "process" in kwargs:
            self._process = kwargs["process"]
            del kwargs["process"]
        else:
            raise Exception("missing process")
        self._primary_buffer = {}
        super(TerminalScreen, self).__init__(*args, **kwargs)

    def write_process_input(self, data):
        self._process.write(data)

    def resize(self, lines=None, columns=None):
        lines = lines or self.lines
        columns = columns or self.columns

        if lines == self.lines and columns == self.columns:
            return  # No changes.

        self.dirty.update(range(lines))

        line_diff = self.lines - lines
        if line_diff > 0:
            bottom = self.first_non_empty_line_from_bottom()
            num_empty_lines = self.lines - 1 - bottom
            if line_diff > num_empty_lines:
                line_diff = line_diff - num_empty_lines
                self.push_screen_into_history(line_diff)
                self.scroll_up(line_diff)
                self.cursor.y -= line_diff

        if columns < self.columns:
            for line in self.buffer.values():
                for x in range(columns, self.columns):
                    line.pop(x, None)

        self.lines, self.columns = lines, columns
        self.set_margins()

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
            self.push_screen_into_history()

        super().erase_in_display(how)

    def first_non_empty_line_from_bottom(self):
        found = -1
        for nz_line in reversed(range(self.lines)):
            text = "".join([c.data for c in self.buffer[nz_line].values()])
            if text and not text.isspace():
                found = nz_line
                break
        return found

    def push_screen_into_history(self, lines=None):
        if self.alt_screen_mode():
            return
        if lines is None:
            # find the first non-empty line from the botton
            lines = self.first_non_empty_line_from_bottom() + 1
        self.history.top.extend(copy(self.buffer[y]) for y in range(lines))
        self.offset += lines

    def scroll_up(self, n):
        logger.debug("scroll_up {}".format(n))
        top, bottom = self.margins or Margins(0, self.lines - 1)
        for y in range(top, bottom + 1):
            if y + n > bottom:
                self.buffer[y].clear()
            else:
                self.buffer[y] = copy(self.buffer[y + n])
        self.dirty.update(range(self.lines))

    def scroll_down(self, n):
        logger.debug("scoll_down {}".format(n))
        top, bottom = self.margins or Margins(0, self.lines - 1)
        for y in reversed(range(top, bottom + 1)):
            if y - n < top:
                self.buffer[y].clear()
            else:
                self.buffer[y] = copy(self.buffer[y - n])
        self.dirty.update(range(self.lines))


class TerminalStream(pyte.Stream):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.csi["S"] = "scroll_up"
        self.csi["T"] = "scroll_down"

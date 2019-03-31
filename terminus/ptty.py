import re
import sys
import logging
import unicodedata
from copy import copy
from collections import defaultdict, deque, namedtuple
from wcwidth import wcwidth, wcswidth

import pyte
from pyte.screens import StaticDefaultDict, Margins
from pyte import modes as mo
from pyte import graphics as g
from pyte import control as ctrl


if sys.platform.startswith("win"):
    from winpty import PtyProcess
    is_windows = True
else:
    from ptyprocess import PtyProcess
    is_windows = False


logger = logging.getLogger('Terminus')


FG_AIXTERM = {
    90: "light_black",
    91: "light_red",
    92: "light_green",
    93: "light_brown",
    94: "light_blue",
    95: "light_magenta",
    96: "light_cyan",
    97: "light_white"
}

BG_AIXTERM = {
    100: "light_black",
    101: "light_red",
    102: "light_green",
    103: "light_brown",
    104: "light_blue",
    105: "light_magenta",
    106: "light_cyan",
    107: "light_white"
}


FILE_PARAM_PATTERN = re.compile(
    r"^File=(?P<arguments>[^:]*?):(?P<data>[a-zA-Z0-9\+/=]*)(?P<cr>\r?)$"
)


def reverse_fg_bg(fg, bg):
    fg, bg = bg, fg
    if fg == "default":
        fg = "reverse_default"
    if bg == "default":
        bg = "reverse_default"
    return fg, bg


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
    reverse = False

    if buffer_line:
        last_index = max(buffer_line.keys()) + 1
    else:
        last_index = 0

    for i in range(last_index):
        if is_wide_char:
            is_wide_char = False
            continue
        char = buffer_line[i]
        is_wide_char = wcswidth(char.data) >= 2

        if counter == 0:
            counter = i
            text = " " * i

        if fg != char.fg or bg != char.bg or reverse != char.reverse:
            if reverse:
                fg, bg = reverse_fg_bg(fg, bg)
            yield text, start, counter, fg, bg
            fg = char.fg
            bg = char.bg
            reverse = char.reverse
            text = char.data
            start = counter
        else:
            text += char.data

        counter += 1

    if reverse:
        fg, bg = reverse_fg_bg(fg, bg)
    yield text, start, counter, fg, bg


class Char(namedtuple("Char", [
    "data",
    "fg",
    "bg",
    "bold",
    "italics",
    "underscore",
    "strikethrough",
    "reverse",
    "linefeed"
])):

    __slots__ = ()

    def __new__(cls, data, fg="default", bg="default", bold=False,
                italics=False, underscore=False,
                strikethrough=False, reverse=False, linefeed=False):
        return super(Char, cls).__new__(cls, data, fg, bg, bold, italics,
                                        underscore, strikethrough, reverse, linefeed)


class Cursor(object):
    __slots__ = ("x", "y", "attrs", "hidden")

    def __init__(self, x, y, attrs=Char(" ")):
        self.x = x
        self.y = y
        self.attrs = attrs
        self.hidden = False


if is_windows:

    class TerminalPtyProcess(PtyProcess):

        pass

else:

    class TerminalPtyProcess(PtyProcess):

        def read(self, size):
            b = super().read(size)
            return b.decode("utf-8", "ignore")

        def write(self, s):
            b = s.encode("utf-8", "backslashreplace")
            return super().write(b)


class TerminalScreen(pyte.Screen):

    @property
    def default_char(self):
        reverse = mo.DECSCNM in self.mode
        return Char(data=" ", fg="default", bg="default", reverse=reverse)

    def __init__(self, *args, **kwargs):
        if "process" in kwargs:
            self._process = kwargs["process"]
            del kwargs["process"]
        else:
            raise Exception("missing process")

        if "clear_callback" in kwargs:
            self._clear_callback = kwargs["clear_callback"]
            del kwargs["clear_callback"]
        else:
            raise Exception("missing clear_callback")

        if "reset_callback" in kwargs:
            self._reset_callback = kwargs["reset_callback"]
            del kwargs["reset_callback"]
        else:
            raise Exception("missing reset_callback")

        if "history" in kwargs:
            history = kwargs["history"]
            del kwargs["history"]
        else:
            history = 100

        self.primary_buffer = {}
        self.history = deque(maxlen=history)
        self._alternate_buffer_mode = False
        super().__init__(*args, **kwargs)

    # @property
    # def display(self):
    #     pass

    def reset(self):
        super().reset()
        self.cursor = Cursor(0, 0)
        self.history.clear()
        self._reset_callback()

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
                self.push_lines_into_history(line_diff)
                self.scroll_up(line_diff)
                self.cursor.y -= line_diff

        # if columns < self.columns:
        #     for line in self.buffer.values():
        #         for x in range(columns, self.columns):
        #             line.pop(x, None)

        self.lines, self.columns = lines, columns
        self.set_margins()
        self.tabstops = set(range(8, self.columns, 8))

    def set_margins(self, top=None, bottom=None):
        if (top is None or top == 0) and bottom is None:
            # https://github.com/selectel/pyte/commit/676610b43954b644c05823371df6daf87caafdad
            self.margins = None
        else:
            super().set_margins(top, bottom)

    def set_mode(self, *modes, **kwargs):
        super().set_mode(*modes, **kwargs)
        if 1049 << 5 in self.mode and not self.alternate_buffer_mode:
            self.alternate_buffer_mode = True
            self.switch_to_screen(alt=True)

    def reset_mode(self, *modes, **kwargs):
        super().reset_mode(*modes, **kwargs)
        if 1049 << 5 not in self.mode and self.alternate_buffer_mode:
            self.alternate_buffer_mode = False
            self.switch_to_screen(alt=False)

    # def define_charset(self, code, mode):
    #     pass

    # def shift_in(self):
    #     pass

    # def shift_out(self):
    #     pass

    def draw(self, data):
        """
        Terminus alters the logic to better support double width chars and linefeed marker
        """
        data = data.translate(
            self.g1_charset if self.charset else self.g0_charset)

        for char in data:
            char_width = wcwidth(char)
            if (self.cursor.x == self.columns and char_width >= 1)  \
                    or (self.cursor.x == self.columns - 1 and char_width >= 2):
                if mo.DECAWM in self.mode:
                    last = self.buffer[self.cursor.y][self.columns - 1]
                    self.buffer[self.cursor.y][self.columns - 1] = \
                        last._replace(linefeed=True)
                    self.dirty.add(self.cursor.y)
                    self.carriage_return()
                    self.linefeed()
                elif char_width > 0:
                    self.cursor.x -= char_width

            if mo.IRM in self.mode and char_width > 0:
                self.insert_characters(char_width)

            line = self.buffer[self.cursor.y]
            if char_width == 1:
                if is_windows and self.cursor.x == self.columns - 1:
                    # always put a linefeed marker when cursor is at the last column
                    line[self.cursor.x] = self.cursor.attrs._replace(data=char, linefeed=True)
                else:
                    line[self.cursor.x] = self.cursor.attrs._replace(data=char)

            elif char_width == 2:
                line[self.cursor.x] = self.cursor.attrs._replace(data=char)
                if is_windows and self.cursor.x == self.columns - 2:
                    # always put a linefeed marker when the next char is at the last column
                    line[self.cursor.x + 1] = self.cursor.attrs._replace(data="", linefeed=True)
                elif self.cursor.x + 1 < self.columns:
                    line[self.cursor.x + 1] = self.cursor.attrs._replace(data="")

            elif char_width == 0 and unicodedata.combining(char):
                # unfornately, sublime text doesn't render decomposed double char correctly
                pos = None
                for (row, col) in [
                        (self.cursor.y, self.cursor.x),
                        (self.cursor.y - 1, self.columns)]:
                    if row < 0:
                        continue
                    if col >= 2:
                        last = line[col - 2]
                        if wcswidth(last.data) >= 2:
                            pos = (row, col - 2)
                            break
                    if col >= 1:
                        last = line[col - 1]
                        pos = (row, col - 1)
                        break

                if pos:
                    normalized = unicodedata.normalize("NFC", last.data + char)
                    self.buffer[pos[0]][pos[1]] = last._replace(data=normalized)
                    self.dirty.add(pos[0])
            else:
                break

            if char_width > 0:
                self.cursor.x = min(self.cursor.x + char_width, self.columns)

        self.dirty.add(self.cursor.y)

    # def set_title(self, param):
    #     pass

    # def set_icon_name(self, param):
    #     pass

    # def carriage_return(self):
    #     pass

    def index(self):
        if not self.alternate_buffer_mode and self.cursor.y == self.lines - 1:
            self.push_lines_into_history(1)
        super().index()

    # def reverse_index(self):
    #     pass

    # def linefeed(self):
    #     pass

    # def tab(self):
    #     pass

    # def backspace(self):
    #    pass

    # def save_cursor(self):
    #     pass

    # def restore_cursor(self):
    #     pass

    # def insert_lines(self, count=None):
    #     pass

    # def delete_lines(self, count=None):
    #     pass

    # def insert_characters(self, count=None):
    #     pass

    # def delete_characters(self, count=None):
    #     pass

    # def erase_characters(self, count=None):
    #     pass

    # def erase_in_line(self, how=0, private=False):
    #     pass

    def erase_in_display(self, how=0, *args, **kwargs):
        # dump the screen to history
        # check also https://github.com/selectel/pyte/pull/108

        if not self.alternate_buffer_mode and \
                (how == 2 or (how == 0 and self.cursor.x == 0 and self.cursor.y == 0)):
            self.push_lines_into_history()

        super().erase_in_display(how)

        if how == 3:
            self.history.clear()
            self._clear_callback()

    # def set_tab_stop(self):
    #     pass

    # def clear_tab_stop(self, how=0):
    #     pass

    # def ensure_hbounds(self):
    #     pass

    # def ensure_vbounds(self, use_margins=None):
    #     pass

    # def cursor_up(self, count=None):
    #     pass

    # def cursor_up1(self, count=None):
    #     pass

    # def cursor_down(self, count=None):
    #     pass

    # def cursor_down1(self, count=None):
    #     pass

    # def cursor_back(self, count=None):
    #     pass

    # def cursor_forward(self, count=None):
    #     pass

    # def cursor_position(self, line=None, column=None):
    #     pass

    # def cursor_to_column(self, column=None):
    #     pass

    # def cursor_to_line(self, line=None):
    #     pass

    # def bell(self, *args):
    #     pass

    # def alignment_display(self):
    #     pass

    def select_graphic_rendition(self, *attrs):
        """Set display attributes.

        :param list attrs: a list of display attributes to set.
        """
        replace = {}

        # Fast path for resetting all attributes.
        if not attrs or attrs == (0, ):
            self.cursor.attrs = self.default_char
            return
        else:
            attrs = list(reversed(attrs))

        while attrs:
            attr = attrs.pop()
            if attr == 0:
                # Reset all attributes.
                replace.update(self.default_char._asdict())
            elif attr in g.FG_ANSI:
                replace["fg"] = g.FG_ANSI[attr]
            elif attr in g.BG:
                replace["bg"] = g.BG_ANSI[attr]
            elif attr in g.TEXT:
                attr = g.TEXT[attr]
                replace[attr[1:]] = attr.startswith("+")
            elif attr in g.FG_AIXTERM:
                replace.update(fg=FG_AIXTERM[attr])
            elif attr in g.BG_AIXTERM:
                replace.update(bg=BG_AIXTERM[attr])
            elif attr in (g.FG_256, g.BG_256):
                key = "fg" if attr == g.FG_256 else "bg"
                try:
                    n = attrs.pop()
                    if n == 5:    # 256.
                        m = attrs.pop()
                        replace[key] = g.FG_BG_256[m]
                    elif n == 2:  # 24bit.
                        # This is somewhat non-standard but is nonetheless
                        # supported in quite a few terminals. See discussion
                        # here https://gist.github.com/XVilka/8346728.
                        replace[key] = "{0:02x}{1:02x}{2:02x}".format(
                            attrs.pop(), attrs.pop(), attrs.pop())
                except IndexError:
                    pass

        self.cursor.attrs = self.cursor.attrs._replace(**replace)

    # def report_device_attributes(self, mode=0, **kwargs):
    #     pass

    # def report_device_status(self, mode):
    #     pass

    def write_process_input(self, data):
        self._process.write(data)

    # def debug(self, *args, **kwargs):
    #     pass

    def scroll_up(self, n):
        top, bottom = self.margins or Margins(0, self.lines - 1)
        for y in range(top, bottom + 1):
            if y + n > bottom:
                self.buffer[y].clear()
            else:
                self.buffer[y] = copy(self.buffer[y + n])
        self.dirty.update(range(self.lines))

    def scroll_down(self, n):
        top, bottom = self.margins or Margins(0, self.lines - 1)
        for y in reversed(range(top, bottom + 1)):
            if y - n < top:
                self.buffer[y].clear()
            else:
                self.buffer[y] = copy(self.buffer[y - n])
        self.dirty.update(range(self.lines))

    def handle_iterm_protocol(self, param):
        m = FILE_PARAM_PATTERN.match(param)
        if m:
            arguments = {}
            for pair in m.group("arguments").split(";"):
                if "=" not in pair:
                    continue
                key, value = pair.split("=", 1)
                arguments[key] = value

            data = m.group("data")
            cr = m.group("cr")

            self.show_image_callback(data, arguments, cr)

    def set_show_image_callback(self, callback):
        self.show_image_callback = callback

    @property
    def alternate_buffer_mode(self):
        return self._alternate_buffer_mode

    @alternate_buffer_mode.setter
    def alternate_buffer_mode(self, value):
        self._alternate_buffer_mode = value

    def switch_to_screen(self, alt=False):
        if alt:
            self.primary_buffer["buffer"] = self.buffer
            self.primary_buffer["history"] = self.history
            self.primary_buffer["cursor"] = self.cursor
            self.buffer = defaultdict(lambda: StaticDefaultDict(self.default_char))
            self.history = deque(maxlen=0)
            self.cursor = Cursor(0, 0)
        else:
            self.buffer = self.primary_buffer["buffer"]
            self.history = self.primary_buffer["history"]
            self.cursor = self.primary_buffer["cursor"]

        self.dirty.update(range(self.lines))

    def first_non_empty_line_from_bottom(self):
        found = -1
        for nz_line in reversed(range(self.lines)):
            text = "".join([c.data for c in self.buffer[nz_line].values()])
            if text and not text.isspace():
                found = nz_line
                break
        return found

    def push_lines_into_history(self, count=None):
        if self.alternate_buffer_mode:
            return
        if count is None:
            # find the first non-empty line from the botton
            count = self.first_non_empty_line_from_bottom() + 1
        self.history.extend(copy(self.buffer[y]) for y in range(count))


PLAIN_TEXT = "plain_text"
OSC_PARAM = "osc_param"


class TerminalStream(pyte.Stream):

    def __init__(self, *args, **kwargs):
        self.csi["S"] = "scroll_up"
        self.csi["T"] = "scroll_down"
        self.osc = {
            "0": "set_title",
            "01": "set_icon_name",
            "02": "set_title",
            "1337": "handle_iterm_protocol"
        }
        self._osc_termination_pattern = re.compile(
            "|".join(map(re.escape, [ctrl.ST_C0, ctrl.ST_C1, ctrl.BEL, ctrl.CR])))
        self.yield_what = None
        super().__init__(*args, **kwargs)

    def _parser_fsm(self):
        """
        Override to support "imgcat"
        """
        basic = self.basic
        listener = self.listener
        draw = listener.draw
        debug = listener.debug

        ESC, CSI_C1 = ctrl.ESC, ctrl.CSI_C1
        OSC_C1 = ctrl.OSC_C1
        SP_OR_GT = ctrl.SP + ">"
        NUL_OR_DEL = ctrl.NUL + ctrl.DEL
        CAN_OR_SUB = ctrl.CAN + ctrl.SUB
        ALLOWED_IN_CSI = "".join([ctrl.BEL, ctrl.BS, ctrl.HT, ctrl.LF,
                                  ctrl.VT, ctrl.FF, ctrl.CR])
        OSC_TERMINATORS = set([ctrl.ST_C0, ctrl.ST_C1, ctrl.BEL, ctrl.CR])

        def create_dispatcher(mapping):
            return defaultdict(lambda: debug, dict(
                (event, getattr(listener, attr))
                for event, attr in mapping.items()))

        basic_dispatch = create_dispatcher(basic)
        sharp_dispatch = create_dispatcher(self.sharp)
        escape_dispatch = create_dispatcher(self.escape)
        csi_dispatch = create_dispatcher(self.csi)
        osc_dispatch = create_dispatcher(self.osc)

        while True:
            # ``True`` tells ``Screen.feed`` that it is allowed to send
            # chunks of plain text directly to the listener, instead
            # of this generator.
            char = yield True

            if char == ESC:
                # Most non-VT52 commands start with a left-bracket after the
                # escape and then a stream of parameters and a command; with
                # a single notable exception -- :data:`escape.DECOM` sequence,
                # which starts with a sharp.
                #
                # .. versionchanged:: 0.4.10
                #
                #    For compatibility with Linux terminal stream also
                #    recognizes ``ESC % C`` sequences for selecting control
                #    character set. However, in the current version these
                #    are noop.
                char = yield
                if char == "[":
                    char = CSI_C1  # Go to CSI.
                elif char == "]":
                    char = OSC_C1  # Go to OSC.
                else:
                    if char == "#":
                        sharp_dispatch[(yield)]()
                    if char == "%":
                        self.select_other_charset((yield))
                    elif char in "()":
                        code = yield
                        if self.use_utf8:
                            continue

                        # See http://www.cl.cam.ac.uk/~mgk25/unicode.html#term
                        # for the why on the UTF-8 restriction.
                        listener.define_charset(code, mode=char)
                    else:
                        escape_dispatch[char]()
                    continue    # Don't go to CSI.

            if char in basic:
                # Ignore shifts in UTF-8 mode. See
                # http://www.cl.cam.ac.uk/~mgk25/unicode.html#term for
                # the why on UTF-8 restriction.
                if (char == ctrl.SI or char == ctrl.SO) and self.use_utf8:
                    continue

                basic_dispatch[char]()
            elif char == CSI_C1:
                # All parameters are unsigned, positive decimal integers, with
                # the most significant digit sent first. Any parameter greater
                # than 9999 is set to 9999. If you do not specify a value, a 0
                # value is assumed.
                #
                # .. seealso::
                #
                #    `VT102 User Guide <http://vt100.net/docs/vt102-ug/>`_
                #        For details on the formatting of escape arguments.
                #
                #    `VT220 Programmer Ref. <http://vt100.net/docs/vt220-rm/>`_
                #        For details on the characters valid for use as
                #        arguments.
                params = []
                current = ""
                private = False
                while True:
                    char = yield
                    if char == "?":
                        private = True
                    elif char in ALLOWED_IN_CSI:
                        basic_dispatch[char]()
                    elif char in SP_OR_GT:
                        pass  # Secondary DA is not supported atm.
                    elif char in CAN_OR_SUB:
                        # If CAN or SUB is received during a sequence, the
                        # current sequence is aborted; terminal displays
                        # the substitute character, followed by characters
                        # in the sequence received after CAN or SUB.
                        draw(char)
                        break
                    elif char.isdigit():
                        current += char
                    else:
                        params.append(min(int(current or 0), 9999))

                        if char == ";":
                            current = ""
                        else:
                            if private:
                                csi_dispatch[char](*params, private=True)
                            else:
                                csi_dispatch[char](*params)
                            break  # CSI is finished.
            elif char == OSC_C1:
                code = ""
                while True:
                    char = yield
                    if char in OSC_TERMINATORS or char == ";":
                        break
                    code += char

                if code == "R":
                    continue  # Reset palette. Not implemented.
                elif code == "P":
                    continue  # Set palette. Not implemented.

                param = ""
                if char == ";":
                    while True:
                        block = yield OSC_PARAM
                        if block in OSC_TERMINATORS:
                            break
                        param += block

                osc_dispatch[code](param)

            elif char not in NUL_OR_DEL:
                draw(char)

    def feed(self, data):
        send = self._parser.send
        draw = self.listener.draw
        match_text = self._text_pattern.match
        search_osc = self._osc_termination_pattern.search
        yield_what = self.yield_what

        length = len(data)
        offset = 0
        while offset < length:
            if yield_what == PLAIN_TEXT:
                match = match_text(data, offset)
                if match:
                    start, offset = match.span()
                    draw(data[start:offset])
                else:
                    yield_what = None
            elif yield_what == OSC_PARAM:
                match = search_osc(data, offset)
                if match:
                    start, end = match.span()
                    send(data[offset:start])
                    send(data[start])
                    offset = start + 1
                    yield_what = None
                else:
                    send(data[offset:])
                    offset = length
            else:
                yield_what = send(data[offset:offset + 1])
                offset += 1

        self.yield_what = yield_what

import sublime
import sublime_plugin

import math
import time
import logging

from .ptty import segment_buffer_line
from .utils import rev_wcwidth, highlight_key
from .terminal import Terminal, CONTINUATION


logger = logging.getLogger('Terminus')


class TerminusViewEventListener(sublime_plugin.EventListener):

    def on_activated(self, view):
        terminal = Terminal.from_id(view.id())
        if terminal:
            # a hack to fix a bracket highlighter bug
            # https://github.com/facelessuser/BracketHighlighter/issues/488
            # TODO: remove this hack for BH
            view.settings().set("bracket_highlighter.clone_locations", {})
            return

        settings = view.settings()
        if not settings.has("terminus_view.args") or settings.get("terminus.detached"):
            return

        kwargs = settings.get("terminus_view.args")
        if "cmd" not in kwargs:
            return

        sublime.set_timeout(lambda: view.run_command("terminus_activate", kwargs), 100)


class TerminusActivateCommand(sublime_plugin.TextCommand):

    def run(self, _, **kwargs):
        view = self.view
        terminal = Terminal()
        terminal.attach_view(view)
        terminal.activate(view, **kwargs)


class TerminusViewMixinx:

    def ensure_position(self, edit, row, col=0):
        view = self.view
        lastrow = view.rowcol(view.size())[0]
        if lastrow < row:
            view.insert(edit, view.size(), "\n" * (row - lastrow))
        line_region = view.line(view.text_point(row, 0))
        lastcol = view.rowcol(line_region.end())[1]
        if lastcol < col:
            view.insert(edit, line_region.end(), " " * (col - lastcol))


class TerminusRenderCommand(sublime_plugin.TextCommand, TerminusViewMixinx):
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
        self.update_lines(edit, terminal)
        viewport_y = view.settings().get("terminus.viewport.y", 0)
        if viewport_y < view.viewport_position()[1] + view.line_height():
            self.trim_trailing_spaces(edit, terminal)
            self.trim_history(edit, terminal)
            view.run_command("terminus_show_cursor")
        if screen.title != terminal.title:
            if screen.title:
                terminal.title = screen.title
            else:
                terminal.title = terminal.default_title
        screen.dirty.clear()
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
            self.decolorize_line(row)
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
                self.decolorize_line(view.rowcol(line)[0])
            view.erase(edit, tail_region)


class TerminusShowCursor(sublime_plugin.TextCommand, TerminusViewMixinx):

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
        view.settings().set("terminus.viewport.y", y)
        view.set_viewport_position((0, y), True)


class TerminusInsertCommand(sublime_plugin.TextCommand):

    def run(self, edit, point, character):
        self.view.insert(edit, point, character)

import sublime
import sublime_plugin

import time
import math
import logging

from .const import CONTINUATION
from .ptty import segment_buffer_line
from .terminal import Terminal
from .utils import rev_wcwidth, highlight_key

logger = logging.getLogger('Terminus')


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
        settings = sublime.load_settings("Terminus.sublime-settings")
        self.scrollback_history_size = settings.get("scrollback_history_size", 10000)
        self.brighten_bold_text = settings.get("brighten_bold_text", False)

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

        current_title = view.name()
        if terminal.title:
            if current_title != terminal.title:
                view.set_name(terminal.title)
        else:
            if screen.title:
                if current_title != screen.title:
                    view.set_name(screen.title)
            else:
                if current_title != terminal.default_title:
                    view.set_name(terminal.default_title)

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
            fg, bg, bold = s[3:]
            if fg != "default" or bg != "default":
                if bold and self.brighten_bold_text:
                    if fg != "default" and fg != "reverse_default" and not fg.startswith("light_"):
                        fg = "light_" + fg
                    if bg != "default" and bg != "reverse_default" and not bg.startswith("light_"):
                        bg = "light_" + bg
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

        screen = terminal.screen
        lastrow = view.rowcol(view.size())[0]
        n = self.scrollback_history_size
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


class TerminusShowCursorCommand(sublime_plugin.TextCommand, TerminusViewMixin):

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
        view.set_viewport_position((0, y), False)


class TerminusCleanupCommand(sublime_plugin.TextCommand):
    def run(self, edit, by_user=False):
        logger.debug("cleanup")
        view = self.view
        terminal = Terminal.from_id(view.id())
        if not terminal:
            return

        if view.settings().get("terminus_view.finished"):
            return

        # to avoid double cancel
        view.settings().set("terminus_view.finished", True)

        view.run_command("terminus_render")

        # process might became orphan, make sure the process is terminated
        terminal.kill()
        process = terminal.process

        if terminal.auto_close:
            view.run_command("terminus_close")

        view.run_command("terminus_trim_trailing_lines")

        if by_user:
            view.run_command("append", {"characters": "[Cancelled]"})

        elif terminal.timeit:
            if process.exitstatus == 0:
                view.run_command(
                    "append",
                    {"characters": "[Finished in {:0.2f}s]".format(
                        time.time() - terminal.start_time)})
            else:
                view.run_command(
                    "append",
                    {"characters": "[Finished in {:0.2f}s with exit code {}]".format(
                        time.time() - terminal.start_time, process.exitstatus)})
        elif process.exitstatus is not None:
            view.run_command(
                "append",
                {"characters": "process is terminated with return code {}.".format(
                    process.exitstatus)})

        view.sel().clear()

        if not terminal.show_in_panel and view.settings().get("result_file_regex"):
            # if it is a tab based build, we will to refocus to enable next_result
            window = view.window()
            if window:
                active_view = window.active_view()
                view.window().focus_view(view)
                if active_view:
                    view.window().focus_view(active_view)

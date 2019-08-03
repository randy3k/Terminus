# -*- coding: utf-8 -*-
import logging
import re
import webbrowser
from pathlib import Path

import sublime
import sublime_plugin

from .terminal import CONTINUATION, Terminal
from .utils import highlight_key

logger = logging.getLogger('Terminus')

rex = re.compile(r'''(?x)
    \b(?:
        https?://(?:(?:[a-zA-Z0-9\-_]+(?:\.[a-zA-Z0-9\-._]+)+)|localhost)|  # http://
        www\.[a-zA-Z0-9\-_]+(?:\.[a-zA-Z0-9\-._]+)+                         # www.
    )
    /?[a-zA-Z0-9\-._?,!'(){}\[\]/+&@%$#=:"|~;]*                             # url path and query string
    [a-zA-Z0-9\-_~:/#@$*+=]                                                 # allowed end chars
    ''')
rexf = re.compile(r'(?i)(?:(?<=\"))(?P<file>[a-zA-Z0-9\-_\./\\]+)(?:(?=\"))(?:\",)?(?:\sline\s)(?P<line>[0-9]+)')

URL_POPUP = """
<style>
body {
    margin: 0px;
}
div {
    border: 1px;
    border-style: solid;
    border-color: grey;
}
</style>
<body>
<div>
<a href="open">
<img width="20%" height="20%" src="res://Packages/Terminus/images/link.png" />
</a>
</div>
</body>
"""


def find_common(view, event=None, pt=None):
    if event:
        pt = view.window_to_text((event["x"], event["y"]))
    line = view.line(pt)

    line.a = max(line.a, pt - 1024)
    line.b = pt + 1024

    text = view.substr(line)
    original_text = text
    text = text.replace(CONTINUATION + "\n", "")
    return text, line, pt, original_text


def find_url(view, event=None, pt=None):
    text, line, pt, _ = find_common(view, event, pt)
    for match in rex.finditer(text):
        if match.start() <= (pt - line.a) and match.end() >= (pt - line.a):
            url = text[match.start():match.end()]
            if url[0:3] == "www":
                return "http://" + url
            else:
                return url
    return None


def find_file(view, event=None, pt=None):
    text, line, pt, _ = find_common(view, event, pt)
    for m in rexf.finditer(text):
        return '%s:%s' % (m.group('file'), m.group('line'))
    return None


def find_something(view, event=None, pt=None):
    thing = find_url(view, event, pt)
    if thing:
        return thing, 'url'
    thing = find_file(view, event, pt)
    if thing:
        path, line = thing.split(':')
        full_path = path = Path(path)
        if not path.is_absolute():
            for folder in view.window().folders():
                full_path = Path(folder).joinpath(path)
                if full_path.exists():
                    break
        if full_path.exists():
            return '%s:%s' % (full_path, line), 'file'
    return (None, None)


def find_url_region(view, event=None, pt=None, reg=rex):
    text, line, pt, original_text = find_common(view, event, pt)
    for match in reg.finditer(text):
        if match.start() <= (pt - line.a) and match.end() >= (pt - line.a):
            a = match.start()
            b = match.end()
            for marker in re.finditer(CONTINUATION + "\n", original_text):
                if a <= marker.start() and b >= marker.start():
                    b += len(CONTINUATION) + 1
            return (line.a + a, line.a + b)
    return None


class TerminusMouseEventListener(sublime_plugin.EventListener):

    type_reg = {'url': rex, 'file': rexf}

    def on_text_command(self, view, command_name, args):
        terminal = Terminal.from_id(view.id())
        if not terminal:
            return
        if command_name == "drag_select":
            if len(args) == 1 and args["event"]["button"] == 1:  # simple click
                return ("terminus_click", args)

    def on_hover(self, view, point, hover_zone):
        terminal = Terminal.from_id(view.id())
        if not terminal:
            return
        if hover_zone != sublime.HOVER_TEXT:
            return
        for_open, type_ = find_something(view, pt=point)

        if not for_open:
            return

        def on_navigate(action):
            if action == "open":
                webbrowser.open_new_tab(for_open)

        def on_navigate_file(action):
            if action == "open":
                view.window().open_file(for_open, sublime.ENCODED_POSITION)

        def on_hide():
            if link_key:
                view.erase_regions(link_key)

        regexp = self.type_reg[type_]
        if type_ == 'url':
            on_nav = on_navigate
        else:
            on_nav = on_navigate_file

        url_region = find_url_region(view, reg=regexp, pt=point)

        link_key = None
        if url_region:
            link_key = highlight_key(view)
            view.add_regions(
                link_key,
                [sublime.Region(*url_region)],
                "meta",
                flags=sublime.DRAW_NO_FILL
                | sublime.DRAW_NO_OUTLINE
                | sublime.DRAW_SOLID_UNDERLINE,
            )

        view.show_popup(
            URL_POPUP,
            sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            location=point,
            on_navigate=on_nav,
            on_hide=on_hide,
        )


class TerminusOpenContextUrlCommand(sublime_plugin.TextCommand):
    def run(self, edit, event):
        for_open, type_ = find_something(self.view, event)
        if type_ == 'url':
            webbrowser.open_new_tab(for_open)
        elif type_ == 'file':
            self.view.window().open_file(for_open, sublime.ENCODED_POSITION)

    def is_enable(self, *args, **kwargs):
        terminal = Terminal.from_id(self.view.id())
        return terminal is not None

    def is_visible(self, event):
        terminal = Terminal.from_id(self.view.id())
        return terminal is not None and find_something(self.view, event)[0] is not None

    def description(self, event):
        for_open, type_ = find_something(self.view, event)
        if len(for_open) > 64:
            for_open = for_open[0:64] + "..."
        return "Open " + for_open

    def want_event(self):
        return True


class TerminusClickCommand(sublime_plugin.TextCommand):
    """Reset cursor position if the click is occured below the last row."""

    def run_(self, edit, args):
        view = self.view
        window = view.window()
        if not window:
            return

        event = args["event"]
        pt = view.window_to_text((event["x"], event["y"]))
        if pt == view.size():
            if view.text_to_window(view.size())[1] + view.line_height() < event["y"]:
                logger.debug("reset cursor")
                window.focus_group(window.active_group())
                window.focus_view(view)
                view.run_command("terminus_show_cursor", {"scroll": False})
                return

        if any(s.contains(pt) for s in view.sel()):
            # disable dragging
            view.sel().clear()

        view.run_command("drag_select", args)


class TerminusOpenImageCommand(sublime_plugin.TextCommand):
    def want_event(self):
        return True

    def is_enable(self, *args, **kwargs):
        terminal = Terminal.from_id(self.view.id())
        return terminal is not None

    def is_visible(self, event):
        terminal = Terminal.from_id(self.view.id())
        return terminal is not None and self.find_phantom(event) is not None

    def find_phantom(self, event):
        view = self.view
        terminal = Terminal.from_id(view.id())
        if not terminal:
            return
        pt = view.window_to_text((event["x"], event["y"]))
        cord = view.text_to_window(pt)
        if cord[1] < event["y"]:
            for pid in terminal.images:
                region = view.query_phantom(pid)[0]
                if region.end() == pt:
                    return pid
        else:
            # the right click happens at the lower half of the images
            row, col = view.rowcol(pt)
            cord = view.text_to_window(view.text_point(row - 1, 0))
            pt = view.window_to_text((event["x"], cord[1]))
            for pid in terminal.images:
                region = view.query_phantom(pid)[0]
                if region.end() == pt:
                    return pid
        return None

    def run(self, edit, event):
        view = self.view
        terminal = Terminal.from_id(view.id())
        image_url = terminal.images[self.find_phantom(event)]
        webbrowser.open_new_tab("file://{}".format(image_url))

    def description(self, event):
        return "Open Image"

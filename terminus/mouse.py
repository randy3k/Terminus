import re
import webbrowser

import sublime_plugin

from .terminal import Terminal, CONTINUATION


rex = re.compile(
    r'''(?x)
    \b(?:
        https?://(?:(?:[a-zA-Z0-9\-_]+(?:\.[a-zA-Z0-9\-._]+)+)|localhost)|  # http://
        www\.[a-zA-Z0-9\-_]+(?:\.[a-zA-Z0-9\-._]+)+                         # www.
    )
    /?[a-zA-Z0-9\-._?,!'(){}\[\]/+&@%$#=:"|~;]*                             # url path and query string
    [a-zA-Z0-9\-_~:/#@$*+=]                                                 # allowed end chars
    ''')


class TerminusOpenContextUrlCommand(sublime_plugin.TextCommand):
    def run(self, edit, event):
        url = self.find_url(event)
        webbrowser.open_new_tab(url)

    def is_enable(self, *args, **kwargs):
        terminal = Terminal.from_id(self.view.id())
        return terminal is not None

    def is_visible(self, event):
        return self.find_url(event) is not None

    def find_url(self, event):
        pt = self.view.window_to_text((event["x"], event["y"]))
        line = self.view.line(pt)

        line.a = max(line.a, pt - 1024)
        line.b = pt + 1024

        text = self.view.substr(line)
        text = text.replace(CONTINUATION + "\n", "")
        it = rex.finditer(text)

        for match in it:
            if match.start() <= (pt - line.a) and match.end() >= (pt - line.a):
                url = text[match.start():match.end()]
                if url[0:3] == "www":
                    return "http://" + url
                else:
                    return url

        return None

    def description(self, event):
        url = self.find_url(event)
        if len(url) > 64:
            url = url[0:64] + "..."
        return "Open " + url

    def want_event(self):
        return True


class TerminusClickCommand(sublime_plugin.TextCommand):

    def run_(self, edit, args):
        self.view.run_command("drag_select", args)


class TerminusMouseEventHandler(sublime_plugin.EventListener):

    def on_text_command(self, view, command_name, args):
        terminal = Terminal.from_id(view.id())
        if not terminal:
            return
        if command_name == "drag_select":
            if len(args) == 1 and args["event"]["button"] == 1:  # simple click
                return ("terminus_click", args)

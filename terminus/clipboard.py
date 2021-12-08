import sublime
import sublime_plugin
from Default.paste_from_history import ClipboardHistory

g_clipboard_history = ClipboardHistory()


class TerminusClipboardHistoryUpdater(sublime_plugin.EventListener):

    def on_post_text_command(self, view, name, args):
        if view.settings().get('is_widget'):
            return

        if name == 'copy' or name == 'cut':
            g_clipboard_history.push_text(sublime.get_clipboard())

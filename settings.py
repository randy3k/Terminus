import sublime
import sublime_plugin


class ConsoleEditSettingsListener(sublime_plugin.EventListener):
    def on_post_window_command(self, window, command, args):
        if command == "edit_settings":
            base = args.get("base_file", "")
            if base.endswith("sublime-keymap") and "/Console/Default" in base:
                w = sublime.active_window()
                w.focus_group(0)
                w.run_command("open_file", {"file": "${packages}/Console/Default.sublime-keymap"})
                w.focus_group(1)


class ConsoleEditSettingsCommand(sublime_plugin.WindowCommand):
    """
    For some reasons, the command palette doesn't trigger `on_post_window_command` for
    dev version of Sublime Text. The command palette would call `gs_edit_settings` and
    subsequently trigger `on_post_window_command`.
    """
    def run(self, **kwargs):
        self.window.run_command("edit_settings", kwargs)

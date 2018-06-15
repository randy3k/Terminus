import sublime
import sublime_plugin

import os

from .tools.theme_generator import generate_theme_file


class ConsoleGenerateTheme(sublime_plugin.WindowCommand):
    def run(self, remove=False):
        settings = sublime.load_settings("Console.sublime-settings")

        theme = settings.get("theme", "default")
        if theme == "user":
            variables = settings.get("user_theme_colors", {})
        elif theme == "default":
            variables = settings.get("default_theme_colors", {})
        else:
            variables = {}

        path = os.path.join(
            sublime.packages_path(),
            "User",
            "Console",
            "Console.sublime-color-scheme"
        )
        if remove:
            os.unlink(path)
            print("Theme removed: {}".format(path))
            sublime.status_message("Theme removed")
        else:
            generate_theme_file(path, variables=variables, ansi_scopes=False)
            print("Theme generated: {}".format(path))
            sublime.status_message("Theme generated")


def plugin_loaded():

    settings = sublime.load_settings("Console.sublime-settings")

    path = os.path.join(
        sublime.packages_path(),
        "User",
        "Console",
        "Console.sublime-color-scheme"
    )

    if settings.get("theme", "default") != "default":
        if not os.path.isfile(path):
            sublime.active_window().run_command("console_generate_theme")

    _cached_theme = settings.get("theme", "default")
    _cached_user_theme_colors = settings.get("user_theme_colors", {}).copy()

    def on_change():
        nonlocal _cached_theme, _cached_user_theme_colors
        theme = settings.get("theme", "default")
        user_theme_colors = settings.get("user_theme_colors", {}).copy()
        if theme != _cached_theme or user_theme_colors != _cached_user_theme_colors:
            sublime.active_window().run_command("console_generate_theme")
            _cached_user_theme_colors = user_theme_colors
            _cached_theme = theme

    settings.clear_on_change("user_theme_colors")
    settings.add_on_change("user_theme_colors", on_change)

import sublime
import sublime_plugin

import os
import json

from .tools.theme_generator import generate_theme_file


THEMES = os.path.join(os.path.dirname(__file__), "themes")


class ConsoleSelectTheme(sublime_plugin.WindowCommand):
    def run(self, theme=None):
        if theme:
            if theme not in ["default", "user"]:
                themefile = os.path.join(THEMES, "{}.json".format(theme))
                if not os.path.isfile(themefile):
                    raise IOError("{} not found".format(themefile))

            settings = sublime.load_settings("Console.sublime-settings")
            settings.set("theme", theme)
            sublime.save_settings("Console.sublime-settings")

        else:
            self.themes = ["default", "user"] + \
                sorted([f.replace(".json", "") for f in os.listdir(THEMES) if f.endswith(".json")])
            self.window.show_quick_panel(
                self.themes,
                self.on_selection)

    def on_selection(self, index):
        theme = self.themes[index]
        self.window.run_command("console_select_theme", {"theme": theme})


class ConsoleGenerateTheme(sublime_plugin.WindowCommand):
    def run(self, theme=None, remove=False):
        settings = sublime.load_settings("Console.sublime-settings")

        if not theme:
            theme = settings.get("theme", "default")
        if theme == "user":
            variables = settings.get("user_theme_colors", {})
        elif theme == "default":
            # variables = settings.get("default_theme_colors", {})
            variables = {}
        else:
            themefile = os.path.join(THEMES, "{}.json".format(theme))
            if not os.path.isfile(themefile):
                raise IOError("{} not found".format(themefile))

            with open(themefile, "r") as f:
                theme_data = json.load(f)
                variables = theme_data["theme_colors"]

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

    _cached = {
        "theme": settings.get("theme", "default"),
        "user_theme_colors": settings.get("user_theme_colors", {}).copy()
    }

    def on_change():
        theme = settings.get("theme", "default")
        user_theme_colors = settings.get("user_theme_colors", {}).copy()
        if theme != _cached["theme"] or user_theme_colors != _cached["user_theme_colors"]:
            print("will generate")
            sublime.active_window().run_command("console_generate_theme")
            _cached["theme"] = theme
            _cached["user_theme_colors"] = user_theme_colors

    settings.clear_on_change("user_theme_colors")
    settings.add_on_change("user_theme_colors", on_change)

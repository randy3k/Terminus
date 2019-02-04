import sublime
import sublime_plugin

import os
import json

from Terminus.tools.theme_generator import generate_theme_file, ANSI_COLORS
from .utils import settings_on_change


THEMES = os.path.join(os.path.dirname(__file__), "..", "themes")


class TerminusSelectThemeCommand(sublime_plugin.WindowCommand):
    def run(self, theme=None):
        if theme:
            if theme not in ["default", "user"]:
                themefile = os.path.join(THEMES, "{}.json".format(theme))
                if not os.path.isfile(themefile):
                    raise IOError("{} not found".format(themefile))

            settings = sublime.load_settings("Terminus.sublime-settings")
            settings.set("theme", theme)
            sublime.save_settings("Terminus.sublime-settings")

        else:
            self.themes = ["default", "user"] + \
                sorted([f.replace(".json", "") for f in os.listdir(THEMES) if f.endswith(".json")])
            settings = sublime.load_settings("Terminus.sublime-settings")
            self.original_theme = settings.get("theme", "default")
            try:
                selected_index = self.themes.index(self.original_theme)
            except Exception:
                selected_index = 0
            self.window.show_quick_panel(
                self.themes,
                self.on_selection,
                selected_index=selected_index,
                on_highlight=lambda x: sublime.set_timeout_async(lambda: self.on_selection(x)))

    def on_selection(self, index):
        if index == -1:
            self.window.run_command(
                "terminus_select_theme",
                {"theme": self.original_theme})
            return
        theme = self.themes[index]
        self.window.run_command("terminus_select_theme", {"theme": theme})


class TerminusGenerateThemeCommand(sublime_plugin.WindowCommand):
    def run(self, theme=None, remove=False, force=False):
        settings = sublime.load_settings("Terminus.sublime-settings")

        if not theme:
            theme = settings.get("theme", "default")
        if theme == "user":
            variables = settings.get("user_theme_colors", {})
            for key, value in list(variables.items()):
                if key.isdigit():
                    variables[ANSI_COLORS[int(key)]] = value
                    del variables[key]

        elif theme == "default":
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
            "Terminus",
            "Terminus.sublime-color-scheme"
        )

        path256 = os.path.join(
            sublime.packages_path(),
            "User",
            "Terminus.sublime-color-scheme"
        )

        if remove:
            if os.path.isfile(path):
                os.unlink(path)
                print("Theme removed: {}".format(path))
            if os.path.isfile(path256):
                os.unlink(path256)
                print("Theme removed: {}".format(path256))
            sublime.status_message("Theme {} removed".format(theme))
        else:
            if settings.get("256color", False):
                if force or not os.path.isfile(path256):
                    generate_theme_file(
                        path256, ansi_scopes=True, color256_scopes=True, pretty=False)
                    print("Theme {} generated: {}".format(theme, path256))
            else:
                if os.path.isfile(path256):
                    os.unlink(path256)

            generate_theme_file(path, variables=variables, ansi_scopes=False, color256_scopes=False)
            print("Theme {} generated: {}".format(theme, path))

            sublime.status_message("Theme generated")


def plugin_loaded():
    # this is a hack to remove the deprecated sublime-color-scheme files
    deprecated_paths = [
        os.path.join(sublime.packages_path(), "User", "Console.sublime-color-scheme"),
        os.path.join(sublime.packages_path(), "User", "SublimelyTerminal.sublime-color-scheme")
    ]
    for deprecated_path in deprecated_paths:
        if os.path.isfile(deprecated_path):
            os.unlink(deprecated_path)

    settings = sublime.load_settings("Terminus.sublime-settings")

    path = os.path.join(
        sublime.packages_path(),
        "User",
        "Terminus",
        "Terminus.sublime-color-scheme"
    )

    if settings.get("theme", "default") != "default":
        if not os.path.isfile(path):
            sublime.active_window().run_command("terminus_generate_theme")

    settings_on_change(settings, ["256color", "user_theme_colors", "theme"])(
        lambda _: sublime.active_window().run_command("terminus_generate_theme")
    )


def plugin_unloaded():
    settings = sublime.load_settings("Terminus.sublime-settings")
    settings_on_change(settings, ["256color", "user_theme_colors", "theme"], clear=True)

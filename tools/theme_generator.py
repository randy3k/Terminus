import os
import json
import pyte
from collections import OrderedDict

TEMPLATE = OrderedDict(
    name="Console",
    variables=OrderedDict(),
    globals=OrderedDict(),
    rules=[]
)


def next_color(color_text):
    """
    Given a color string "#xxxxxy", returns its next color "#xxxxx{y+1}".
    """
    hex_value = int(color_text[1:], 16)
    if hex_value == 16777215:  # #ffffff
        return "#fffffe"
    else:
        return "#{:6x}".format(hex_value+1).replace(" ", "0")


ANSI_COLORS = [
    "black",
    "red",
    "green",
    "brown",
    "blue",
    "magenta",
    "cyan",
    "white",
    "light_black",
    "light_red",
    "light_green",
    "light_brown",
    "light_blue",
    "light_magenta",
    "light_cyan",
    "light_white"
]


def generate_theme_file(
        path, variables={}, globals={}, ansi_scopes=True, color256_scopes=False):
    COLOR_SCHEME = TEMPLATE.copy()

    _colors16 = OrderedDict()
    for i in range(8):
        _colors16[ANSI_COLORS[i]] = "#{}".format(pyte.graphics.FG_BG_256[i])

    for i in range(8):
        _colors16["light_" + ANSI_COLORS[i]] = "#{}".format(
            pyte.graphics.FG_BG_256[8 + i])

    if variables:
        COLOR_SCHEME["variables"].update(_colors16)
        COLOR_SCHEME["variables"].update(variables)

    if globals:
        COLOR_SCHEME["globals"].update(globals)

    # There is a bug/feature of add_regions: if the background of a scope is exactly the same as the
    # background of the theme. The foregound and background colors would be inverted. check
    # https://github.com/SublimeTextIssues/Core/issues/817

    if "background" in COLOR_SCHEME["variables"]:
        background = COLOR_SCHEME["variables"]["background"]
        COLOR_SCHEME["variables"]["background"] = next_color(background)
        COLOR_SCHEME["globals"]["background"] = background
    else:
        background = None

    colors = OrderedDict()
    if ansi_scopes:
        colors.update(_colors16)
        colors["default"] = "#default"
    if color256_scopes:
        for i, rgb in enumerate(pyte.graphics.FG_BG_256):
            colors[rgb] = "#{}".format(rgb)

    for u, ucolor in colors.items():
        for v, vcolor in colors.items():
            if u in ANSI_COLORS:
                ucolor = "var({})".format(u)
            elif ucolor == "#default":
                ucolor = "var(foreground)"
            if v in ANSI_COLORS:
                vcolor = "var({})".format(v)
            elif vcolor == "#default" or vcolor == background:
                vcolor = "var(background)"
            rule = {}
            rule["scope"] = "console.{}.{}".format(u, v)
            rule["foreground"] = ucolor
            rule["background"] = vcolor
            COLOR_SCHEME["rules"].append(rule)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(json.dumps(COLOR_SCHEME, indent=4))


if __name__ == "__main__":

    path = os.path.join(os.path.dirname(__file__), "..", "Console.sublime-color-scheme")
    variables = {
        "background": "#262626",
        "foreground": "#ffffff"
    }
    globals = {
        "background": "var(background)",
        "foreground": "var(foreground)",
        "caret": "white",
        "selection": "grey"
    }

    generate_theme_file(path, variables=variables, globals=globals)

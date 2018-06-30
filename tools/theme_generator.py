import os
import json
import pyte
from copy import deepcopy
from collections import OrderedDict

TEMPLATE = OrderedDict(
    name="Terminus",
    variables=OrderedDict(),
    globals=OrderedDict()
)


def next_color(color_text):
    """
    Given a color string "#xxxxxy", returns its next color "#xxxx{xy+1}".
    """
    hex_value = int(color_text[5:], 16)
    if hex_value == 255:  # ff
        return color_text[:5] + "fe"
    else:
        return color_text[:5] + "{:2x}".format(hex_value + 1).replace(" ", "0")


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
        path, variables={}, globals={}, ansi_scopes=True, color256_scopes=False, pretty=True):
    COLOR_SCHEME = deepcopy(TEMPLATE)

    _colors16 = OrderedDict()
    for i in range(16):
        _colors16[ANSI_COLORS[i]] = "#{}".format(pyte.graphics.FG_BG_256[i])

    if variables:
        if "caret" not in variables and "foreground" in variables:
            variables["caret"] = variables["foreground"]

        # make sure the variables are in order
        COLOR_SCHEME["variables"].update(variables)
        COLOR_SCHEME["variables"].update(_colors16)
        COLOR_SCHEME["variables"].update(variables)

    if globals:
        COLOR_SCHEME["globals"].update(globals)

    # There is a bug/feature of add_regions
    # if the background of a scope is exactly the same as the background of the theme.
    # The foregound and background colors would be inverted. check
    # https://github.com/SublimeTextIssues/Core/issues/817

    if "background" in COLOR_SCHEME["variables"]:
        background = COLOR_SCHEME["variables"]["background"]
        COLOR_SCHEME["variables"]["background"] = next_color(background)
        COLOR_SCHEME["globals"]["background"] = background
    else:
        background = None

    for key, value in COLOR_SCHEME["variables"].items():
        if key == "background":
            continue
        if value == background:
            COLOR_SCHEME["variables"][key] = next_color(value)

    colors = OrderedDict()
    if ansi_scopes:
        colors.update(_colors16)
        colors["default"] = "#default"
        colors["reverse_default"] = "#reverse_default"
    if color256_scopes:
        for i, rgb in enumerate(pyte.graphics.FG_BG_256):
            colors[rgb] = "#{}".format(rgb)

    if colors:
        COLOR_SCHEME["rules"] = []

    for u, ucolor in colors.items():
        for v, vcolor in colors.items():
            if u in ANSI_COLORS:
                ucolor = "var({})".format(u)
            elif ucolor == "#default":
                ucolor = "var(foreground)"
            elif ucolor == "#reverse_default":
                ucolor = "var(background)"
            if v in ANSI_COLORS:
                vcolor = "var({})".format(v)
            elif vcolor == "#default" or vcolor == background:
                vcolor = "var(background)"
            elif vcolor == "#reverse_default":
                vcolor = "var(foreground)"
            rule = {}
            rule["scope"] = "terminus.{}.{}".format(u, v)
            rule["foreground"] = ucolor
            rule["background"] = vcolor
            COLOR_SCHEME["rules"].append(rule)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        if pretty:
            f.write(json.dumps(COLOR_SCHEME, indent=4))
        else:
            f.write(json.dumps(COLOR_SCHEME))


if __name__ == "__main__":

    path = os.path.join(os.path.dirname(__file__), "..", "Terminus.sublime-color-scheme")
    variables = {
        "background": "#262626",
        "foreground": "#ffffff",
        "caret": "white",
        "selection": "#444444",
        "selection_foreground": "#ffffff"
    }
    globals = {
        "background": "var(background)",
        "foreground": "var(foreground)",
        "caret": "var(caret)",
        "selection": "var(selection)",
        "selection_foreground": "var(selection_foreground)",
        "selection_corner_style": "square",
        "selection_border_width": "0"
    }

    generate_theme_file(path, variables=variables, globals=globals)

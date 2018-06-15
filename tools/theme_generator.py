import os
import json
import pyte

TEMPLATE = {
    "name": "Console",
    "variables":
    {
        "background": "#262626",
        "foreground": "#ffffff"
    },
    "globals":
    {
        "background": "to be set",
        "foreground": "var(foreground)",
        "caret": "white",
        "selection": "grey"
    },
    "rules":
    [
    ]
}


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
    "white"
]


def generate_theme_file(
        path, variables={}, ansi_scopes=True, color256_scopes=False, pretty=False):
    COLOR_SCHEME = TEMPLATE.copy()

    _colors16 = {}
    for i in range(8):
        _colors16[ANSI_COLORS[i]] = "#{}".format(pyte.graphics.FG_BG_256[i])

    for i in range(8):
        _colors16["light_" + ANSI_COLORS[i]] = "#{}".format(
            pyte.graphics.FG_BG_256[8 + i])

    _colors16["default"] = "#default"
    COLOR_SCHEME["variables"].update(_colors16)
    COLOR_SCHEME["variables"].update(variables)

    # There is a bug/feature of add_regions: if the background of a scope is exactly the same as the
    # background of the theme. The foregound and background colors would be inverted. check
    # https://github.com/SublimeTextIssues/Core/issues/817

    background = COLOR_SCHEME["variables"]["background"]
    COLOR_SCHEME["variables"]["background"] = next_color(background)
    COLOR_SCHEME["globals"]["background"] = background

    colors = {}
    if ansi_scopes:
        colors.update(_colors16)
    if color256_scopes:
        for i, rgb in enumerate(pyte.graphics.FG_BG_256):
            colors[rgb] = "#{}".format(rgb)

    for u, ucolor in colors.items():
        for v, vcolor in colors.items():
            if u.replace("light_", "") in ANSI_COLORS:
                ucolor = "var({})".format(u)
            elif ucolor == "#default":
                ucolor = "var(foreground)"
            if v.replace("light_", "") in ANSI_COLORS:
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
    generate_theme_file(path)

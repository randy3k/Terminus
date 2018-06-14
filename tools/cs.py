import os
import json
import pyte

color_scheme = {
    "name": "Console",
    "variables":
    {
        "bgcolor": "#262625",
        "fgcolor": "#ffffff"
    },
    "globals":
    {
        "background": "#262626",
        "foreground": "#ffffff",
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

colors = {}

for i in range(8):
    colors[ANSI_COLORS[i]] = "#{}".format(pyte.graphics.FG_BG_256[i])

for i in range(8):
    colors["light" + ANSI_COLORS[i]] = "#{}".format(
        pyte.graphics.FG_BG_256[8 + i])

color_scheme["variables"].update(colors)

colors["default"] = "#default"

# for i, rgb in enumerate(pyte.graphics.FG_BG_256):
#     colors[rgb] = "#{}".format(rgb)


background = color_scheme["globals"]["background"]

for u, ucolor in colors.items():
    for v, vcolor in colors.items():
        if u.replace("light", "") in ANSI_COLORS:
            ucolor = "var({})".format(u)
        elif ucolor == "#default":
            ucolor = "var(fgcolor)"
        if v.replace("light", "") in ANSI_COLORS:
            vcolor = "var({})".format(v)
        elif vcolor == "#default" or vcolor == background:
            vcolor = "var(bgcolor)"
        rule = {}
        rule["scope"] = "console.{}.{}".format(u, v)
        rule["foreground"] = ucolor
        rule["background"] = vcolor
        color_scheme["rules"].append(rule)


path = os.path.join(os.path.dirname(__file__), "..", "Console-ansi.sublime-color-scheme")
with open(path, "wb", buffering=0) as f:
    f.write(json.dumps(color_scheme, indent=4).encode("utf-8"))

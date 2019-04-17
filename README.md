# Bring a real terminal to Sublime Text

<a href="https://packagecontrol.io/packages/Terminus"><img src="https://packagecontrol.herokuapp.com/downloads/Terminus.svg"></a>
<a href="https://www.paypal.me/randy3k/5usd" title="Donate to this project using Paypal"><img src="https://img.shields.io/badge/paypal-donate-blue.svg" /></a>
<a href="https://liberapay.com/randy3k/donate"><img src="http://img.shields.io/liberapay/receives/randy3k.svg?logo=liberapay"></a>

The first cross platform terminal for Sublime Text.

<table>
    <tr>
        <th>Unix shell</th>
        <th>Cmd.exe</th>
    </tr>
    <tr>
        <td width="50%">
            <a href="https://user-images.githubusercontent.com/1690993/41784539-03534fdc-760e-11e8-845d-3d133a559df5.gif">
                <img src="https://user-images.githubusercontent.com/1690993/41784539-03534fdc-760e-11e8-845d-3d133a559df5.gif" width="100%">
            </a>
        </td>
        <td width="50%">
            <a href="https://user-images.githubusercontent.com/1690993/41786131-a625d870-7612-11e8-882d-f1574184faba.gif">
                <img src="https://user-images.githubusercontent.com/1690993/41786131-a625d870-7612-11e8-882d-f1574184faba.gif" width="100%">
            </a>
        </td>
    </tr>
    <tr>
        <th>Terminal in panel</th>
        <th>Support <a href="https://www.iterm2.com/documentation-images.html">showing images</a></th>
    </tr>
    <tr>
        <td width="50%">
            <a href="https://user-images.githubusercontent.com/1690993/41784748-a7ed9d90-760e-11e8-8979-dd341933f1bb.gif">
                <img src="https://user-images.githubusercontent.com/1690993/41784748-a7ed9d90-760e-11e8-8979-dd341933f1bb.gif" width="100%">
            </a>
        </td>
        <td width="50%">
            <img src="https://user-images.githubusercontent.com/1690993/51725223-1dfa3780-202f-11e9-9600-6e24b78d562d.png" width="100%">
        </td>
    </tr>
</table>

This package is heavily inspired by [TerminalView](https://github.com/Wramberg/TerminalView). Compare with TerminalView, this has

- Windows support
- continuous history
- easily customizable themes (see Terminus Utilities)
- unicode support
- 256 colors support
- better xterm support
- terminal panel
- [imgcat](https://www.iterm2.com/documentation-images.html) support (PS: it also works on Linux / WSL)

## Installation

Package Control.

### Getting started

- run `Terminus: Open Default Shell in View`


## User Key Bindings

You may find these key bindings useful. To edit, run `Preferences: Terminus Key Bindings`.
Check the details for the arguments of `terminus_open` below.


- toggle terminal panel
```json
[
    { "keys": ["alt+`"], "command": "toggle_terminus_panel" }
]
```

- open a terminal view at current file directory
```json
[
    { 
        "keys": ["ctrl+alt+t"], "command": "terminus_open", "args": {
            "cwd": "${file_path:${folder}}"
        }
    }
]
```
or by passing a custom `cmd`, say `ipython`
```json
[
    { 
        "keys": ["ctrl+alt+t"], "command": "terminus_open", "args": {
            "cmd": "ipython",
            "cwd": "${file_path:${folder}}"
        }
    }
]
```

- open terminal in a split view by using [Origami](https://github.com/SublimeText/Origami)'s `carry_file_to_pane`

```json
[
    {
        "keys": ["ctrl+alt+t"],
        "command": "terminus_open",
        "args": {
            "post_window_hooks": [
                ["carry_file_to_pane", {"direction": "down"}]
            ]
        }
    }
]
```

## User Commands in Palette

- run `Preferences: Terminus Command Palette`. Check the details for the arguments of `terminus_open` below

```json
[
    {
        "caption": "Terminus: Open Default Shell at Current Location",
        "command": "terminus_open",
        "args"   : {
            "cwd": "${file_path:${folder}}"
        }
    }
]
```
or by passing custom `cmd`, say `ipython`

```json
[
    {
        "caption": "Terminus: Open iPython",
        "command": "terminus_open",
        "args"   : {
            "cmd": "ipython",
            "cwd": "${file_path:${folder}}",
            "title": "iPython"
        }
    }
]
```

- open terminal in a split view by using [Origami](https://github.com/SublimeText/Origami)'s `carry_file_to_pane`

```json
[
    {
        "caption": "Terminus: Open Default Shell in Split View",
        "command": "terminus_open",
        "args": {
            "post_window_hooks": [
                ["carry_file_to_pane", {"direction": "down"}]
            ]
        }
    }
]
```

## User Build System

Use `Terminus` as a build system. For example, the following can be added to your project settings to run a bash command.

```json
{
    "build_systems":
    [
        {
            "cmd":
            [
                "bash", "-c", "echo helloworld"
            ],
            "name": "Hello World",
            "target": "terminus_open",
            "working_dir": "$folder",
            "auto_close": false
        }
    ]
}
```

## Ctrl-W to close terminal

Following keybind can be considered if one wants to use `ctrl+w` to close terminals.

```
{ 
    "keys": ["ctrl+w"], "command": "terminus_close", "context": [{ "key": "terminus_view"}]
}
```

## Alt-Left/Right to move between words (Unix)

- Bash: add the following in `.bash_profile` or `.bashrc`
```
if [ $TERM_PROGRAM == "Terminus-Sublime" ]; then
    bind '"\e[1;3C": forward-word'
    bind '"\e[1;3D": backward-word'
fi
```

- Zsh: add the following in `.zshrc`
```
if [ $TERM_PROGRAM == "Terminus-Sublime" ]; then
    bindkey "\e[1;3C" forward-word
    bindkey "\e[1;3D" backward-word
fi
```

Some programs, such as julia, does not recognize the standard keycodes for `alt+left` and `alt+right`. You could
bind them to `alt+b` and `alt+f` respectively
```json
[
    { "keys": ["alt+left"], "command": "terminus_keypress", "args": {"key": "b", "alt": true}, "context": [{"key": "terminus_view"}] },
    { "keys": ["alt+right"], "command": "terminus_keypress", "args": {"key": "f", "alt": true}, "context": [{"key": "terminus_view"}] }
]
```

## Terminus API

- A terminal could be opened using the command `terminus_open` with

```py
window.run_command(
    "terminus_open", {
        "config_name": None,     # the shell config name, use `None` for the default config
        "cmd": None,             # the cmd to execute
        "cwd": None,             # the working directory
        "working_dir": None,     # alias of "cwd"
        "env": {},               # extra environmental variables
        "title": None,           # title of the view, let terminal configures it if leave empty
        "panel_name": None,      # the name of the panel if terminal should be opened in panel
        "tag": None,             # a tag to identify the terminal
        "pre_window_hooks": [],  # a list of window hooks before opening terminal
        "post_window_hooks": [], # a list of window hooks after opening terminal
        "post_view_hooks": [],   # a list of view hooks after opening terminal
        "auto_close": True       # auto close terminal if process exits successfully
    }
)
```

The fields `cmd` and `cwd` understand Sublime Text build system [variables](https://www.sublimetext.com/docs/3/build_systems.html#variables).


- the setting `view.settings().get("terminus_view.tag")` can be used to identify the terminal and 

- keybind can be binded with specific tagged terminal

```json
    {
        "keys": ["ctrl+alt+w"], "command": "terminus_close", "context": [
            { "key": "terminus_view.tag", "operator": "equal", "operand": "YOUR_TAG"}
        ]
    }
```

- text can be sent to the terminal with

```py
window.run_command(
    "terminus_send_string", 
    {
        "string": "ls\n",
        "tag": "<YOUR_TAG>"        # ignore this or set it to None to send text to the first terminal found
        "visible_only": False      # send to visible panels only, default is `False`. Only relevent when `tag` is None
    }
)
```

If `tag` is not provided or is `None`, the text will be sent to the first terminal found in the current window.


## FAQ

### Memory issue

It is known that Terminus sometimes consumes a lot of memory after extensive use. It is because Sublime Text keeps an infinite undo stack. There is virtually no fix unless upstream provides an API to work with the undo stack. Meanwhile, users could execute `Terminus: Reset` to release the memory.

### Color issue when maximizing and minimizing terminal

It is known that the color of the scrollback history will be lost when a terminal is maximized or minimized from or to the panel. There is no fix for this issue.


### Terminal panel background issue

If you are using DA UI and your terminal panel has weired background color,
try playing with the setting `panel_background_color` in `DA UI: Theme
Settings`.

<img src="https://user-images.githubusercontent.com/1690993/41728204-31a9a2a2-7544-11e8-9fb6-a37b59da852a.png" width="50%" />

```json
{
    "panel_background_color": "$background_color"
}
```

### Acknowledgments

This package won't be possible without [pyte](https://github.com/selectel/pyte), [pywinpty](https://github.com/spyder-ide/pywinpty) and [ptyprocess](https://github.com/pexpect/ptyprocess).

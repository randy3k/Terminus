# Bring a real terminal to Sublime Text

<a href="https://packagecontrol.io/packages/Terminus"><img src="https://packagecontrol.herokuapp.com/downloads/Terminus.svg"></a>
<a href="https://www.paypal.me/randy3k/5usd" title="Donate to this project using Paypal"><img src="https://img.shields.io/badge/paypal-donate-blue.svg" /></a>


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

- run `Terminus: Open Default Shell in Tab`

- [OdatNurd](https://github.com/OdatNurd) has made several videos on Terminus. See, for examples,
    - https://www.youtube.com/watch?v=etIJMVIvVgg (most up to date)
    - https://www.youtube.com/watch?v=mV0ghkMwTQc


## Shell configurations

Terminus comes with several shell configurations. The settings file should be quite self explanatory. 


## User Key Bindings

You may find these key bindings useful. To edit, run `Preferences: Terminus Key Bindings`.
Check the details for the arguments of `terminus_open` below.


- toggle terminal panel
```json
[
    { 
        "keys": ["alt+`"], "command": "toggle_terminus_panel"
    }
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

- <kbd>ctrl-w</kbd> to close terminal

Following keybinding can be considered if one wants to use `ctrl+w` to close terminals.

```json
{ 
    "keys": ["ctrl+w"], "command": "terminus_close", "context": [{ "key": "terminus_view"}]
}
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

- open terminal in a split tab by using [Origami](https://github.com/SublimeText/Origami)'s `carry_file_to_pane`

```json
[
    {
        "caption": "Terminus: Open Default Shell in Split Tab",
        "command": "terminus_open",
        "args": {
            "post_window_hooks": [
                ["carry_file_to_pane", {"direction": "down"}]
            ]
        }
    }
]
```

## Terminus Build System

It is possible to use `Terminus` as a build system. The target `terminus_exec` is a drop in replacement of the default target `exec`. It takes exact same arguments as `terminus_open` except that their default values are set differently.

`terminus_cancel_build` is used to cancel the build when user runs `cancel_build` triggered by <kbd>ctrl+c</kbd> (macOS) or <kbd>ctrl+break</kbd> (Windows / Linux).

The following is an example of build system define in project settings that run a python script

```json
{
    "build_systems":
    [
        {
            "name": "Hello World",
            "target": "terminus_exec",
            "cancel": "terminus_cancel_build",
            "cmd": [
                "python", "helloworld.py"
            ],
            "working_dir": "$folder"
        }
    ]
}
```

The same Hello World example could be specified via a `.sublime-build` file.

```json
{
    "target": "terminus_exec",
    "cancel": "terminus_cancel_build",
    "cmd": [
        "python", "helloworld.py"
    ],
    "working_dir": "$folder"
}
```

Instead of `cmd`, user could also specify `shell_cmd`. In macOS and linux, a bash shell will be invoked; and in Windows, cmd.exe will be invoked.

```json
{
    "target": "terminus_exec",
    "cancel": "terminus_cancel_build",
    "shell_cmd": "python helloworld.py",
    // to directly invoke bash command
    // "shell_cmd": "echo helloworld",
    "working_dir": "$folder"
}
```

## Alt-Left/Right to move between words (Unix)

- Bash: add the following in `.bash_profile` or `.bashrc`

    ```sh
    if [ "$TERM_PROGRAM" == "Terminus-Sublime" ]; then
        bind '"\e[1;3C": forward-word'
        bind '"\e[1;3D": backward-word'
    fi
    ```

- Zsh: add the following in `.zshrc`

    ```sh
    if [ "$TERM_PROGRAM" = "Terminus-Sublime" ]; then
        bindkey "\e[1;3C" forward-word
        bindkey "\e[1;3D" backward-word
    fi
    ```

Some programs, such as julia, do not recognize the standard keycodes for `alt+left` and `alt+right`. You could
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
        "shell_cmd": None,       # a script to execute in a shell
                                 # bash on Unix and cmd.exe on Windows
        "cwd": None,             # the working directory
        "working_dir": None,     # alias of "cwd"
        "env": {},               # extra environmental variables
        "title": None,           # title of the view, let terminal configures it if leave empty
        "panel_name": None,      # the name of the panel if terminal should be opened in panel
        "focus": True,           # focus to the panel
        "tag": None,             # a tag to identify the terminal
        "file_regex": None       # the `file_regex` pattern in sublime build system
                                 # see https://www.sublimetext.com/docs/3/build_systems.html
        "line_regex": None       # the `file_regex` pattern in sublime build system
        "pre_window_hooks": [],  # a list of window hooks before opening terminal
        "post_window_hooks": [], # a list of window hooks after opening terminal
        "post_view_hooks": [],   # a list of view hooks after opening terminal
        "view_settings": {},     # extra view settings which are passed to the terminus_view
        "auto_close": "always",  # auto close terminal, possible values are "always" (True), "on_success", and False.
        "cancellable": False,    # allow `cancel_build` command to terminate process, only relevent to panels
        "timeit": False          # display elapsed time when the process terminates
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
        "visible_only": False      # send to visible terminal only, default is `False`. Only relevent when `tag` is None
    }
)
```

If `tag` is not provided or is `None`, the text will be sent to the first terminal found in the current window.


## FAQ

### Memory issue

It is known that Terminus sometimes consumes a lot of memory after extensive use. It is because Sublime Text keeps an infinite undo stack. There is virtually no fix unless upstream provides an API to work with the undo stack. Meanwhile, users could execute `Terminus: Reset` to release the memory.

This issue has been fixed in Sublime Text >= 4114 and Terminus v0.3.20.

### Color issue when maximizing and minimizing terminal

It is known that the color of the scrollback history will be lost when a terminal is maximized or minimized from or to the panel. There is no fix for this issue.


### Terminal panel background issue

If you are using DA UI and your terminal panel has weird background color,
try playing with the setting `panel_background_color` or `panel_text_output_background_color` in `DA UI: Theme
Settings`.

<img src="https://user-images.githubusercontent.com/1690993/41728204-31a9a2a2-7544-11e8-9fb6-a37b59da852a.png" width="50%" />

```json
{
    "panel_background_color": "$background_color"
}
```
Or, to keep the Find and Replace panels unchanged:
```json
"panel_text_output_background_color": "$background_color"
```


### Cmd.exe rendering issue in panel

Due to a upstream bug (may winpty or cmd.exe?), there may be arbitrary empty lines inserted between prompts if the panel is too short. It seems that cmder and powershell are not affected by this bug.


### Acknowledgments

This package won't be possible without [pyte](https://github.com/selectel/pyte), [pywinpty](https://github.com/spyder-ide/pywinpty) and [ptyprocess](https://github.com/pexpect/ptyprocess).

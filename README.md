# Bring a real terminal to Sublime Text

It is a cross platform terminal for Sublime Text which works on Windows, macOS and Linux.

<table>
    <tr>
        <th>macOS/Linux</th>
        <th>Windows</th>
    </tr>
    <tr>
        <td width="50%">
            <a href="https://user-images.githubusercontent.com/1690993/41478796-00ba3cb2-7097-11e8-9de9-bec85213a5c8.gif">
                <img src="https://user-images.githubusercontent.com/1690993/41478796-00ba3cb2-7097-11e8-9de9-bec85213a5c8.gif" width="100%">
            </a>
        </td>
        <td width="50%">
            <a href="https://user-images.githubusercontent.com/1690993/41478434-a46f19c4-7095-11e8-995d-f7b4ef8b9c0e.gif">
                <img src="https://user-images.githubusercontent.com/1690993/41478434-a46f19c4-7095-11e8-995d-f7b4ef8b9c0e.gif" width="100%">
            </a>
        </td>
    </tr>
    <tr>
        <th>Console in panel</th>
        <th></th>
    </tr>
    <tr>
        <td width="50%">
            <a href="https://user-images.githubusercontent.com/1690993/41727462-69fe7ec2-7542-11e8-9c42-64796c1fb023.png">
                <img src="https://user-images.githubusercontent.com/1690993/41727462-69fe7ec2-7542-11e8-9c42-64796c1fb023.png" width="100%">
            </a>
        </td>
        <td width="50%">
        </td>
    </tr>
</table>

This package is heavily inspired by [TerminalView](https://github.com/Wramberg/TerminalView). Compare with TerminalView, this has

- Windows support
- continuous history
- easily customizable themes
- unicode support
- 256 colors support
- better xterm support

### Installation

This package is not yet available via Package Control default channel, you have to add the following repository manually.

- run `Package Control: Add Repository`
- paste

    ```
    https://raw.githubusercontent.com/randy3k/Console/master/package_control.json
    ```
    and hit enter

- then you could install it as usual - `Package Control: Install Package` and search for `Console`


### Keybind to toggle Console Panel

- run `Perferences: Console Key Bindings`
- add the following

```js
{ 
    "keys": ["ctrl+escape"], 
    "command": "toggle_console_panel", 
    "args": {"config_name": "Default", "panel_name": "Console"}
}
```

### Console Panel issue with DA UI

If your console panel has weired background color, try playing with the setting `panel_background_color` in `DA UI: Theme Settings`.

<img src="https://user-images.githubusercontent.com/1690993/41728204-31a9a2a2-7544-11e8-9fb6-a37b59da852a.png" width="50%" />

```js
{
    "panel_background_color": "$background_color"
}
```

### Note to other package developers

A console could be opened using the command `console_open` with
```py
window.run_command(
    "console_open", {
        config_name=None,  # the shell config name, the default config is "Default"
        cmd=None,          # the cmd to execuate if config_name is None
        cwd=None,          # the working directory
        env={},            # extra environmental variables
        title=None,        # title of the view
        panel_name=None,   # the name of the panel if console should be opened in panel
        tag=None           # a tag to identify the console
    }
)
```

Text can be sent to the console with
```py
window.run_command(
    "console_send_string", 
    {
        "string": "ls\n",
        "tag": None        # or the tag which is passed to "console_open"
    }
)
```

### Acknowledgments

This package won't be possible without [pyte](https://github.com/selectel/pyte), [pywinpty](https://github.com/spyder-ide/pywinpty) and [ptyprocess](https://github.com/pexpect/ptyprocess).

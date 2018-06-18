# A Real Terminal for Sublime Text

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
</table>

This package is heavily inspired by [TerminalView](https://github.com/Wramberg/TerminalView). Compare with TerminalView, this has

- Windows support
- Continuous history
- Easily Customizable Themes
- Unicode support
- 256 colors support

### Installation

This package is not yet available via Package Control default channel, you have to add the following repository manually.

- Run `Package Control: Add Repository`
- Paste

    ```
    https://raw.githubusercontent.com/randy3k/Console/master/package_control.json
    ```
    and hit enter

- Run `Package Control: Install Package` and search for `Console`


### Acknowledgments

This package won't be possible without [pyte](https://github.com/selectel/pyte), [pywinpty](https://github.com/spyder-ide/pywinpty) and [ptyprocess](https://github.com/pexpect/ptyprocess).
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

This package heavily inspired by [TerminalView](https://github.com/Wramberg/TerminalView). Compare with TerminalView, this has

- Windows support
- Continuous history
- Easily Customizable Themes
- Unicode support
- 256 colors support (in progress)

### Installation

This package is not yet available via Package Control, you have to install it manually.

- Add the following repository to Package Control (this step is necessary until [this](https://github.com/wbond/package_control_channel/pull/7154) is merged)
    - Run `Package Control: Add Repository`
    - Paste

        ```
        https://gist.githubusercontent.com/randy3k/9f619b9b5c38b901aa8d15a2cd85be79/raw/5d8c1e71d734faa8db71ccbdb33e245bdb04dcc5/dependencies.json
        ```
        and hit enter

- Git Clone this repo to your Sublime Text Packages directory
    ```
    git clone https://github.com/randy3k/Console <PATH/TO/SUBLIMETEXT_PACKAGES/>
    ```
- Run `Package Control: Satisfy Dependencies`
- Restart Sublime Text after done


### Acknowledgments

This package won't be possible without [pyte](https://github.com/selectel/pyte), [pywinpty](https://github.com/spyder-ide/pywinpty) and [ptyprocess](https://github.com/pexpect/ptyprocess).
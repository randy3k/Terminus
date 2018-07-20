# adopted from TerminalView

_KEY_MAP = {
    "enter": "\r",
    "backspace": "\x7f",
    "tab": "\t",
    "space": " ",
    "escape": "\x1b",
    "down": "\x1b[B",
    "up": "\x1b[A",
    "right": "\x1b[C",
    "left": "\x1b[D",
    "home": "\x1b[1~",
    "end": "\x1b[4~",
    "pageup": "\x1b[5~",
    "pagedown": "\x1b[6~",
    "delete": "\x1b[3~",
    "insert": "\x1b[2~",
    "f1": "\x1bOP",
    "f2": "\x1bOQ",
    "f3": "\x1bOR",
    "f4": "\x1bOS",
    "f5": "\x1b[15~",
    "f6": "\x1b[17~",
    "f7": "\x1b[18~",
    "f8": "\x1b[19~",
    "f9": "\x1b[20~",
    "f10": "\x1b[21~",
    "f12": "\x1b[24~",
    "bracketed_paste_mode_start": "\x1b[200~",
    "bracketed_paste_mode_end": "\x1b[201~",
}

_APP_MODE_KEY_MAP = {
    "down": "\x1bOB",
    "up": "\x1bOA",
    "right": "\x1bOC",
    "left": "\x1bOD",
}

_LMN_MODE_KEY_MAP = {
    "enter": "\r\n"
}

_CTRL_KEY_MAP = {
    "up": "\x1b[1;5A",
    "down": "\x1b[1;5B",
    "right": "\x1b[1;5C",
    "left": "\x1b[1;5D",
    "home": "\x1b[1;5~",
    "end": "\x1b[4;5~",
    "pageup": "\x1b[5;5~",
    "pagedown": "\x1b[6;5~",
    "insert": "\x1b[2;5~",
    "delete": "\x1b[3;5~",
    "@": "\x00",
    "`": "\x00",
    "[": "\x1b",
    "{": "\x1b",
    "\\": "\x1c",
    "|": "\x1c",
    "]": "\x1d",
    "}": "\x1d",
    "^": "\x1e",
    "~": "\x1e",
    "_": "\x1f",
    "?": "\x7f",
}

_ALT_KEY_MAP = {
    "up": "\x1b[1;3A",
    "down": "\x1b[1;3B",
    "right": "\x1b[1;3C",
    "left": "\x1b[1;3D"
}

_SHIFT_KEY_MAP = {
    "up": "\x1b[1;2A",
    "down": "\x1b[1;2B",
    "right": "\x1b[1;2C",
    "left": "\x1b[1;2D",
    "tab": "\x1b[Z",
    "home": "\x1b[1;2~",
    "end": "\x1b[4;2~",
    "pageup": "\x1b[5;2~",
    "pagedown": "\x1b[6;2~",
    "insert": "\x1b[2;2~",
    "delete": "\x1b[3;2~"
}


def _get_ctrl_combination_key_code(key):
    key = key.lower()
    if key in _CTRL_KEY_MAP:
        return _CTRL_KEY_MAP[key]
    elif len(key) == 1:
        c = ord(key)
        if (c >= 97) and (c <= 122):
            c = c - ord('a') + 1
            return chr(c)

    return _get_key_code(key)


def _get_alt_combination_key_code(key):
    key = key.lower()
    if key in _ALT_KEY_MAP:
        return _ALT_KEY_MAP[key]

    code = _get_key_code(key)
    return "\x1b" + code


def _get_shift_combination_key_code(key):
    key = key.lower()
    if key in _SHIFT_KEY_MAP:
        return _SHIFT_KEY_MAP[key]

    if key in _KEY_MAP:
        return _KEY_MAP[key]
    return key.upper()


def _get_key_code(key, application_mode=False, new_line_mode=False):
    if application_mode and key in _APP_MODE_KEY_MAP:
        return _APP_MODE_KEY_MAP[key]
    if new_line_mode and key in _LMN_MODE_KEY_MAP:
        return _LMN_MODE_KEY_MAP[key]
    if key in _KEY_MAP:
        return _KEY_MAP[key]
    return key


def get_key_code(
        key,
        ctrl=False, alt=False, shift=False,
        application_mode=False, new_line_mode=False):
    """
    Send keypress to the shell
    """
    if ctrl:
        keycode = _get_ctrl_combination_key_code(key)
    elif alt:
        keycode = _get_alt_combination_key_code(key)
    elif shift:
        keycode = _get_shift_combination_key_code(key)
    else:
        keycode = _get_key_code(key, application_mode, new_line_mode)

    return keycode

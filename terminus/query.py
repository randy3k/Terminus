import sublime
import sublime_plugin

from .core import EXEC_PANEL


class TerminusQueryContextListener(sublime_plugin.EventListener):

    """
    "context": [{ "key": "setting.terminus_view.tag", "operator": "equal", "operand": "inksnw"} ]
    does not work, we implement our own on_query_context
    """

    def on_query_context(self, view, key, operator, operand, match_all):
        if key == "terminus_view.exec_panel_exists":
            if not view.window():
                return
            exists = view.window().find_output_panel(EXEC_PANEL) is not None
            if exists == operand and operator == sublime.OP_EQUAL:
                return True
            elif exists != operand and operator == sublime.OP_NOT_EQUAL:
                return True
        elif key == "terminus_view.exec_panel_visible":
            if not view.window():
                return
            visible = view.window().active_panel() == "output.{}".format(EXEC_PANEL)
            if visible == operand and operator == sublime.OP_EQUAL:
                return True
            elif visible != operand and operator == sublime.OP_NOT_EQUAL:
                return True
        elif key.startswith("terminus_view"):
            tag = view.settings().get(key, None)
            if tag == operand and operator == sublime.OP_EQUAL:
                return True
            elif tag != operand and operator == sublime.OP_NOT_EQUAL:
                return True

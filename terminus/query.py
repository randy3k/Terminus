import sublime
import sublime_plugin


class TerminusQueryContextListener(sublime_plugin.EventListener):

    """
    "context": [{ "key": "setting.terminus_view.tag", "operator": "equal", "operand": "inksnw"} ]
    does not work, we implement our own on_query_context
    """

    def on_query_context(self, view, key, operator, operand, match_all):
        if key.startswith("terminus_view"):
            tag = view.settings().get(key, None)
            if tag == operand and operator == sublime.OP_EQUAL:
                return True
            elif tag != operand and operator == sublime.OP_NOT_EQUAL:
                return True

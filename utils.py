def settings_on_change(settings, keys, clear=True):
    if not isinstance(keys, list):
        keys = [keys]
    _cached = {}
    for key in keys:
        _cached[key] = settings.get(key, None)

    def on_change_factory(key, on_change):
        def _():
            value = settings.get(key)
            if _cached[key] != value:
                try:
                    on_change(value)
                finally:
                    _cached[key] = value

        return _

    def _(on_change):
        for key in keys:
            if clear:
                settings.clear_on_change(key)

            settings.add_on_change(key, on_change_factory(key, on_change))

    return _

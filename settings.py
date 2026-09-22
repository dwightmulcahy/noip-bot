class Settings(object):
    # dictionary of settings
    _settings = {}

    # overrides the `=` operator
    def __setattr__(self, settingName, value):
        self._settings[settingName] = value

    # overrides the accessor operator
    def __getattr__(self, name):
        # this will return `None` if the setting is not in settings object
        return self._settings.get(name)

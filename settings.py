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


if __name__ == '__main__':
    # quickie example...
    settings = Settings()
    settings.isSet = True
    settings.myName = 'is Inigo Montoya'
    settings.action = ['run', 'prepare to die', 'fight']

    if settings.notInSettings is None:
        print('My name')

    print(settings.myName)
    print(settings.action[1])

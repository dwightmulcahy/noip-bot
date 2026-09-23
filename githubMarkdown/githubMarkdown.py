# https://www.markdownguide.org/basic-syntax/
import urllib


class GithubMarkdown:
    def __init__(self):
        pass

    def __wrap(self, text, mdwrapper, level=0) -> str:
        if isinstance(text, str):
            return mdwrapper(f"{level * ' '}{text}")
        if isinstance(text, list):
            return "\n".join([self.__wrap(item, mdwrapper, level + 1) for item in text])
        raise NotImplementedError

    def header(self, text, level=1):
        return self.__wrap(text, lambda t: f"{level * '#'} {t}") + "\n"

    def rule(self):
        return "---\n"

    def italic(self, text):
        return self.__wrap(text, lambda t: f"*{t.strip()}*")

    def bold(self, text):
        return self.__wrap(text, lambda t: f"**{t.strip()}**")

    def strikethrough(self, text):
        return self.__wrap(text, lambda t: f"~~{t.strip()}~~")

    def bolditalics(self, text):
        return self.bold(self.italic(text))

    def paragraph(self, text):
        return self.__wrap(text, lambda t: f"{t}\n\n")

    def linebreak(self, text):
        return self.__wrap(text, lambda t: f"{t}  \n")

    def blockquote(self, text):
        return self.__wrap(text, lambda t: f"> {t}")

    def code(self, text):
        return self.__wrap(text, lambda t: f"`{t}`")

    def codeblock(self, text):
        return self.__wrap(text, lambda t: f"    {t}")

    def link(self, text, url, tooltip=""):
        url = urllib.parse.quote(url, safe="/:")
        urlLink = url if not tooltip else f'{url} "{tooltip}"'
        return f"[{text}]({urlLink})"

    def url(self, text):
        return self.__wrap(urllib.parse.quote(text), lambda t: f"<{t}>")

    def email(self, text):
        return self.url(urllib.parse.quote(text))

    def image(self, text, url, tooltip=""):
        return f"!{self.link(text, url, tooltip)}"

    def escapeMD(self, text):
        mdCharacters = "\\*_{}[]()#+-.!"
        escapedString = []
        for ch in text:
            if ch in mdCharacters:
                escapedString.append(f"\\{ch}")
            else:
                escapedString.append(ch)
        return "".join(escapedString)

    def table(self, text):
        # ways to handle table styling...
        # https://github.com/holoviz/panel/issues/668
        # https://stackoverflow.com/questions/28806135/jekyll-kramdown-how-to-display-table-border
        # <style>
        # table, th, td {
        #     border: 1px solid black;
        # }
        # </style>
        # |     Time    | Number of Trial with Results | Unique Units |
        # |:-----------:|:----------------------------:|:------------:|
        # | 20 Apr 2018 |            30,763            |    21,094    |
        # |  7 Feb 2019 |            34,751            |    23,733    |
        # | 12 Apr 2019 |            35,926            |    24,548    |
        # |             |                              |              |        `
        raise NotImplementedError

    def listordered(self, text, level=(-1)):
        if isinstance(text, str):
            return f"{level * '    '}1. {text}\n"
        if isinstance(text, list):
            return "".join([self.listordered(item, level + 1) for item in text])

    def listunordered(self, text, level=(-1)):
        if isinstance(text, str):
            return f"{level * '    '}* {text}\n"
        if isinstance(text, list):
            return "".join([self.listunordered(item, level + 1) for item in text])

    def tasklist(self, text):
        return self.checklist(text)

    def checklist(self, text, level=(-1)):
        if isinstance(text, str):
            return f"{level * '    '}- [ ] {text}\n"
        if isinstance(text, list):
            return "".join([self.checklist(item, level + 1) for item in text])

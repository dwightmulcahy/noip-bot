import logging
from gmail import Message, GMailWorker, GMail  # https://github.com/paulc/gmail-sender

# Markdown cheatsheet:  https://www.markdownguide.org/cheat-sheet/
from markdown import markdown
from pymdownx import emoji   # https://facelessuser.github.io/pymdown-extensions/

from io import StringIO
from markdown import Markdown


def unmark_element(element, stream=None):
    if stream is None:
        stream = StringIO()
    if element.text:
        stream.write(element.text)
    for sub in element:
        unmark_element(sub, stream)
    if element.tail:
        stream.write(element.tail)
    return stream.getvalue()


# patching Markdown to strip MD from text
Markdown.output_formats["plain"] = unmark_element
__md = Markdown(output_format="plain")
__md.stripTopLevelTags = False


def unmark(text):
    return __md.convert(text)


# GitHub-ish Configuration
# https://guides.github.com/pdfs/markdown-cheatsheet-online.pdf
githubTypeExt = [
    'markdown.extensions.extra',
    'markdown.extensions.nl2br',
    'markdown.extensions.sane_lists',
    'markdown.extensions.attr_list',
    'markdown.extensions.tables',
    'pymdownx.magiclink',
    'pymdownx.betterem',
    'pymdownx.tilde',
    'pymdownx.emoji',
    'pymdownx.tasklist',
    'pymdownx.superfences',
    'pymdownx.saneheaders'
]

githubTypeExtConfig = {
    "pymdownx.magiclink": {
        "repo_url_shortener": True,
        "repo_url_shorthand": True,
        "provider": "github",
        "user": "facelessuser",
        "repo": "pymdown-extensions"
    },
    "pymdownx.tilde": {
        "subscript": False
    },
    "pymdownx.emoji": {
        "emoji_index": emoji.gemoji,
        "emoji_generator": emoji.to_png,
        "alt": "short",
        "options": {
            "attributes": {
                "align": "absmiddle",
                "height": "20px",
                "width": "20px"
            },
            "image_path": "https://assets-cdn.github.com/images/icons/emoji/unicode/",
            "non_standard_image_path": "https://assets-cdn.github.com/images/icons/emoji/"
        }
    }
}


class MarkdownEmailServer:
    def __init__(self, appName: str, gmailSender: str, gmailToken: str, debug=False):
        self.gmail = None
        self.appName = appName
        if debug:
            logging.info(f'Gmail server enabled in DEBUG MODE.')
            self.gmail = GMail(f'{appName} <{gmailSender}>', gmailToken)
        else:
            logging.info(f'Gmail server enabled.')
            self.gmail = GMailWorker(f'{appName} <{gmailSender}>', gmailToken)

    @staticmethod
    def githubMarkdown(text: str) -> str:
        return markdown(text, extensions=githubTypeExt,  extension_configs=githubTypeExtConfig)

    def sendEmail(self, sendTo: str, subject: str = '', body: str = '', htmlBody: str = '', noSig: bool = False) -> bool:
        # if there is no one to send it to or no gmail token return
        if not sendTo or not self.gmail:
            return False

        # sign the email with "sent by ..." if set
        emailSig = '' if noSig else self.githubMarkdown(f"\n\n---\n###### ***Email sent by {self.appName}***\n")

        # create msg bodies in text and html format
        htmlMessageBody = htmlBody
        if not htmlBody:
            htmlMessageBody = self.githubMarkdown(body) + emailSig
        textMessageBody = unmark(htmlMessageBody + emailSig)

        return self.__send(sendTo, subject, textMessageBody, htmlMessageBody)

    def __send(self, sendTo: str, subject: str = '', textBody: str = '', htmlBody: str = ''):
        logging.info(f"sending email titled '{subject}'")
        msg = Message(
            subject=subject,
            to=sendTo,
            text=textBody,
            html=htmlBody,
            reply_to='do@notreply.com',
        )

        try:
            self.gmail.send(msg)
            logging.info(f"Email sent to {sendTo}.")
            return True
        except:
            logging.error(f"Unable to send Email to {sendTo}.")
            # logging.exception(e)
            return False

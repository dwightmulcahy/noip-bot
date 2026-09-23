import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any


class PageContractError(RuntimeError):
    """Raised when No-IP markup no longer matches the supported contract."""


@dataclass(frozen=True, slots=True)
class HostMarkup:
    host_id: str
    hostname: str
    data_update: str
    expires_in_days: int | None
    renewal_available: bool


class _ContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: set[str] = set()
        self.inputs: list[dict[str, str]] = []
        self.buttons: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.hosts: list[dict[str, Any]] = []
        self._ids: list[str] = []
        self._current_host: dict[str, Any] | None = None
        self._host_div_depth = 0

    @staticmethod
    def _attributes(attributes: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attributes}

    def handle_starttag(
        self, tag: str, attributes: list[tuple[str, str | None]]
    ) -> None:
        attrs = self._attributes(attributes)
        element_id = attrs.get("id", "")
        if tag == "form" and element_id:
            self.forms.add(element_id)
        elif tag == "input":
            attrs["parent_ids"] = " ".join(filter(None, self._ids))
            self.inputs.append(attrs)
        elif tag == "button":
            self.buttons.append(attrs)
            match = re.search(r"/ajax/host/(\d+)/touch", attrs.get("hx-get", ""))
            if match:
                for host in self.hosts:
                    if host["host_id"] == match.group(1):
                        host["renewal_available"] = True
                        break
        elif tag == "a":
            self.links.append(attrs)

        classes = set(attrs.get("class", "").split())
        if tag == "div" and "zone-record" in classes:
            label_match = re.search(r"host=(\d+)", attrs.get("data-label", ""))
            self._current_host = {
                "host_id": label_match.group(1) if label_match else "",
                "name": attrs.get("data-name", ""),
                "zone": attrs.get("data-zone", ""),
                "data_update": attrs.get("data-update", ""),
                "expires_in_days": None,
                "renewal_available": False,
            }
            self.hosts.append(self._current_host)
            self._host_div_depth = 1
        elif tag == "div" and self._current_host is not None:
            self._host_div_depth += 1
        elif tag == "span" and self._current_host is not None:
            expiry_match = re.search(
                r"Expires in\s+(\d+)\s+days?", attrs.get("title", "")
            )
            if expiry_match:
                self._current_host["expires_in_days"] = int(expiry_match.group(1))

        if tag not in {
            "area",
            "base",
            "br",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "source",
            "track",
            "wbr",
        }:
            self._ids.append(element_id)

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._current_host is not None:
            self._host_div_depth -= 1
            if self._host_div_depth == 0:
                self._current_host = None
        if self._ids:
            self._ids.pop()


def _parse(html: str) -> _ContractParser:
    parser = _ContractParser()
    parser.feed(html)
    parser.close()
    return parser


def assert_login_contract(html: str) -> None:
    parser = _parse(html)
    names = {field.get("name") for field in parser.inputs}
    button_ids = {button.get("id") for button in parser.buttons}
    missing = []
    if "clogs" not in parser.forms:
        missing.append("form#clogs")
    if "username" not in names:
        missing.append("input[name=username]")
    if "password" not in names:
        missing.append("input[name=password]")
    if "clogs-captcha-button" not in button_ids:
        missing.append("button#clogs-captcha-button")
    if missing:
        raise PageContractError("No-IP login contract missing: " + ", ".join(missing))


def assert_verification_contract(html: str) -> None:
    parser = _parse(html)
    otp_inputs = [
        field for field in parser.inputs if "otp-input" in field.get("parent_ids", "")
    ]
    if len(otp_inputs) != 6:
        raise PageContractError(
            f"No-IP verification contract expected 6 OTP inputs, found {len(otp_inputs)}"
        )


def parse_host_contract(html: str) -> list[HostMarkup]:
    parser = _parse(html)
    if not any(link.get("href") == "/dns/records" for link in parser.links):
        raise PageContractError("No-IP hosts contract missing /dns/records navigation")
    if not parser.hosts:
        raise PageContractError("No-IP hosts contract contains no zone-record rows")

    results = []
    for host in parser.hosts:
        required = ("host_id", "name", "zone", "data_update")
        missing = [name for name in required if not host.get(name)]
        if missing:
            raise PageContractError(
                "No-IP host row missing attributes: " + ", ".join(missing)
            )
        results.append(
            HostMarkup(
                host_id=str(host["host_id"]),
                hostname=f"{host['name']}.{host['zone']}",
                data_update=str(host["data_update"]),
                expires_in_days=host["expires_in_days"],
                renewal_available=bool(host["renewal_available"]),
            )
        )
    return results

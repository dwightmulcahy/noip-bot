"""Verify security floors for packages when they are installed in the image."""

from importlib.metadata import PackageNotFoundError, version


SECURITY_FLOORS = {
    "msgpack": (1, 2, 1),
    "setuptools": (78, 1, 1),
}


def numeric_version(value):
    parts = []
    for component in value.split("."):
        digits = "".join(character for character in component if character.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple((parts + [0, 0, 0])[:3])


def verify_security_floors():
    for package, minimum in SECURITY_FLOORS.items():
        try:
            installed = version(package)
        except PackageNotFoundError:
            print(f"{package}: not installed")
            continue
        if numeric_version(installed) < minimum:
            required = ".".join(map(str, minimum))
            raise RuntimeError(
                f"{package} {installed} is below required security floor {required}"
            )
        print(f"{package}: {installed} (secure)")


if __name__ == "__main__":
    verify_security_floors()

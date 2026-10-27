import os
import subprocess


def normalize_version(value):
    value = (value or "").strip()
    if value.startswith("v") and len(value) > 1 and value[1].isdigit():
        value = value[1:]
    return value


def get_version():
    configured = normalize_version(os.environ.get("APP_VERSION"))
    if configured:
        return configured
    try:
        described = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return "0.0.0-dev"
    return normalize_version(described) or "0.0.0-dev"


def versioned_subject(subject: str, version: str) -> str:
    """Append the application version to an email subject."""
    normalized = normalize_version(version) or "0.0.0-dev"
    return f"{subject} [v{normalized}]"

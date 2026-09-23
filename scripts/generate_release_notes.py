#!/usr/bin/env python3
"""Generate GitHub release notes from conventional commit subjects."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

CONVENTIONAL_COMMIT = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s+(?P<text>.+)$"
)
SECTIONS = {
    "feat": ("✨", "Features"),
    "fix": ("🐛", "Bug fixes"),
    "perf": ("⚡", "Performance"),
    "refactor": ("♻️", "Refactoring"),
    "security": ("🔒", "Security"),
    "docs": ("📚", "Documentation"),
    "test": ("✅", "Tests"),
    "build": ("📦", "Build system"),
    "ci": ("👷", "Continuous integration"),
    "chore": ("🧹", "Maintenance"),
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def previous_tag(tag: str) -> str | None:
    try:
        value = git("describe", "--tags", "--abbrev=0", f"{tag}^")
    except subprocess.CalledProcessError:
        return None
    return value or None


def commit_subjects(tag: str, previous: str | None) -> list[tuple[str, str]]:
    revision = f"{previous}..{tag}" if previous else tag
    output = git("log", revision, "--pretty=format:%h%x09%s")
    subjects = []
    for line in output.splitlines():
        sha, separator, subject = line.partition("\t")
        if separator and not subject.startswith(("Merge ", "Revert ")):
            subjects.append((sha, subject))
    return subjects


def render(tag: str, repository: str) -> str:
    previous = previous_tag(tag)
    grouped: dict[str, list[str]] = defaultdict(list)
    breaking: list[str] = []

    for sha, subject in commit_subjects(tag, previous):
        match = CONVENTIONAL_COMMIT.match(subject)
        if match:
            commit_type = match.group("type")
            scope = match.group("scope")
            text = match.group("text")
            label = f"**{scope}:** {text}" if scope else text
            if match.group("breaking"):
                breaking.append(f"- {label} ({sha})")
            else:
                grouped[commit_type].append(f"- {label} ({sha})")
        else:
            grouped["other"].append(f"- {subject} ({sha})")

    version = tag.removeprefix("v")
    lines = [f"# No-IP Bot {version}", ""]
    if breaking:
        lines.extend(["## 💥 Breaking changes", "", *breaking, ""])
    for commit_type, (icon, title) in SECTIONS.items():
        entries = grouped.pop(commit_type, [])
        if entries:
            lines.extend([f"## {icon} {title}", "", *entries, ""])
    remaining = [entry for entries in grouped.values() for entry in entries]
    if remaining:
        lines.extend(["## 🔧 Other changes", "", *remaining, ""])

    lines.extend(
        [
            "## 🐳 Docker",
            "",
            "```bash",
            f"docker pull dwightmulcahy/noip-bot:{version}",
            "```",
            "",
            "Multi-architecture image: `linux/amd64` and `linux/arm64`.",
            "",
        ]
    )
    if repository and previous:
        comparison = f"https://github.com/{repository}/compare/{previous}...{tag}"
        lines.append(f"**Full changelog:** {comparison}")
    elif repository:
        lines.append(f"**Source:** https://github.com/{repository}/tree/{tag}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        render(args.tag, os.environ.get("GITHUB_REPOSITORY", "")), encoding="utf-8"
    )


if __name__ == "__main__":
    main()

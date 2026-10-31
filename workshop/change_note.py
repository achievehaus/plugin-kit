"""The Workshop change note for a release, from the release's own notes.

Run by the publish-workshop action when its `changenote` input is empty.
The first of these that says something is the note:

1. the version tag's own message, when the tag is annotated
   (`git tag -a v1.2.0 -m "..."`);
2. the version's section of the project's CHANGELOG.md
   (`## 1.2.0`, `## [1.2.0] - 2026-10-30`, `## v1.2.0`);
3. the body of the GitHub release of the tag, when someone wrote one;
4. "<name> v<version>".

Steam's change notes take BBCode, not Markdown: headings, lists, bold,
italics and links are turned into their BBCode, and the rest is plain text.
The note goes into SteamCMD's VDF as one line (the action's rule: no quotes,
no line breaks), so headings and lists are BBCode blocks (`[h2]`, `[list]`)
and keep their layout on the one line; paragraphs run on, a space apart --
Steam's BBCode has no paragraph tag. Trimmed to Steam's limit for a change
note (8000 characters).

Standard library only: it runs from the action's folder on any runner.

    TAG=v1.2.0 NAME="My plugin" python3 change_note.py
"""

import json
import os
import re
import subprocess
import sys

# k_cchPublishedDocumentChangeDescriptionMax in the Steamworks SDK.
STEAM_LIMIT = 8000

# The body the kit's own workflow gives a release when it writes one: not
# notes anybody wrote (crates/pdk/kit/templates/common/dot.github/workflows/plugin.yml).
KIT_RELEASE_BODY = "as achievehaus-plugin pack wrote it"


def version_of(tag):
    """`v1.2.0` -> `1.2.0`."""
    return tag[1:] if tag[:1] in ("v", "V") else tag


def strip_signature(message):
    """A signed tag's message without its signature block."""
    for marker in ("-----BEGIN PGP SIGNATURE-----", "-----BEGIN SSH SIGNATURE-----"):
        i = message.find(marker)
        if i >= 0:
            message = message[:i]
    return message.strip()


def changelog_section(text, version):
    """The body of `version`'s section of a changelog, or "".

    A section is a Markdown heading (any level) whose first word is the
    version -- bare, `v`-prefixed or in brackets, Keep a Changelog's
    `## [1.2.0] - date` -- and runs to the next heading of its level or
    higher."""
    lines = text.replace("\r\n", "\n").split("\n")
    start = level = None
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if not m:
            continue
        depth = len(m.group(1))
        if start is None:
            words = m.group(2).split()
            first = words[0].strip("[]") if words else ""
            if version_of(first) == version:
                start, level = i + 1, depth
        elif depth <= level:
            return "\n".join(lines[start:i]).strip()
    return "\n".join(lines[start:]).strip() if start is not None else ""


def _inline(text):
    """Markdown's inline marks as BBCode."""
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)[^)]*\)", r"[url=\2]\1[/url]", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"[b]{m.group(1) or m.group(2)}[/b]", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"[i]\1[/i]", text)
    text = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"[i]\1[/i]", text)
    return text


def to_bbcode(markdown):
    """Simple Markdown -- headings, bullet and numbered lists, paragraphs,
    bold, italics, links -- as BBCode blocks, on one line."""
    out = []
    para = []
    lst = None  # "list" or "olist"
    items = []

    def close_para():
        if para:
            text = _inline(" ".join(para))
            # Text after text needs a space; after a block it needs none.
            if out and not out[-1].endswith("]"):
                text = " " + text
            out.append(text)
            para.clear()

    def close_list():
        nonlocal lst
        if lst:
            out.append(f"[{lst}]" + "".join(f"[*]{_inline(i)}" for i in items) + f"[/{lst}]")
            items.clear()
            lst = None

    for raw in markdown.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        heading = re.match(r"^(#{1,6})\s+(.*?)\s*#*$", line)
        bullet = re.match(r"^[-*+]\s+(.*)$", line)
        number = re.match(r"^\d+[.)]\s+(.*)$", line)
        if not line:
            close_para()
            close_list()
        elif heading:
            close_para()
            close_list()
            depth = min(len(heading.group(1)), 3)
            out.append(f"[h{depth}]{_inline(heading.group(2))}[/h{depth}]")
        elif bullet or number:
            close_para()
            kind = "list" if bullet else "olist"
            if lst != kind:
                close_list()
                lst = kind
            items.append((bullet or number).group(1))
        elif lst and raw[:1] in (" ", "\t"):
            # A list item's continuation line.
            items[-1] += " " + line
        else:
            close_list()
            para.append(line)
    close_para()
    close_list()
    return "".join(out)


def trim(note, limit=STEAM_LIMIT):
    """`note` within Steam's limit, cut with an ellipsis where it had to be."""
    if len(note) <= limit:
        return note
    return note[: limit - 1].rstrip() + "…"


def choose(name, tag, tag_message="", changelog="", release_body=""):
    """The change note: the first source that says something, as BBCode;
    else `<name> <tag>`."""
    if KIT_RELEASE_BODY in release_body:
        release_body = ""
    for text in (strip_signature(tag_message), changelog, release_body):
        text = (text or "").strip()
        if text:
            return trim(to_bbcode(text))
    return trim(f"{name} {tag}".strip())


def _run(args):
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout if done.returncode == 0 else ""


def read_tag_message(tag):
    """The annotated tag's message; "" for a lightweight tag. The tag is
    fetched again first: actions/checkout leaves a lightweight copy of an
    annotated tag behind (actions/checkout#290)."""
    _run(["git", "fetch", "--quiet", "--force", "--no-tags", "origin", f"refs/tags/{tag}:refs/tags/{tag}"])
    kind = _run(["git", "cat-file", "-t", f"refs/tags/{tag}"]).strip()
    if kind != "tag":
        return ""
    return _run(["git", "tag", "-l", "--format=%(contents)", tag])


def read_changelog(path, version):
    try:
        with open(path, encoding="utf-8") as f:
            return changelog_section(f.read(), version)
    except OSError:
        return ""


def read_release_body(tag):
    if not os.environ.get("GH_TOKEN"):
        return ""
    out = _run(["gh", "release", "view", tag, "--json", "body"])
    try:
        return json.loads(out).get("body") or "" if out else ""
    except ValueError:
        return ""


def main(env=None, out=print):
    env = os.environ if env is None else env
    tag = env.get("TAG", "")
    name = env.get("NAME", "")
    note = choose(
        name,
        tag,
        tag_message=read_tag_message(tag) if tag else "",
        changelog=read_changelog(env.get("CHANGELOG", "CHANGELOG.md"), version_of(tag)),
        release_body=read_release_body(tag) if tag else "",
    )
    out(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())

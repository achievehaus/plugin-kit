#!/usr/bin/env python3
"""Sets a Workshop item's tags to the ones its plugin's source.json makes
(`achievehaus-plugin tags`), after the upload. Called by action.yml.

SteamCMD's `workshop_build_item` has no documented key for tags (Valve's VDF
lists appid, publishedfileid, contentfolder, previewfile, visibility, title,
description, changenote; a `tags` block is reported ignored), and the
`ISteamUGC::SetItemTags` call needs a running Steam client, which a CI runner
has not. The one documented way from a server is the partner Web API:
`IPublishedFileService/UpdateTags`, with a publisher key
(docs/plugins/workshop-findings.md, "Tags").

Only tags under the kit's prefixes (`game:`, `provider:`, `role:`, `api:`)
are the kit's: one of those the manifest no longer makes is removed, and
every other tag -- one the owner set by hand -- is left alone.

    TAGS=role:detector,api:1 ITEM_ID=... APP_ID=5406160 KEY=... workshop_tags.py
    DRY_RUN=1 ...     says what it would send, and asks Steam nothing

The key is never printed: it is scrubbed from any error text.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PARTNER = "https://partner.steam-api.com"
PREFIXES = ("game:", "provider:", "role:", "api:")


class Failed(Exception):
    pass


def parse_list(text):
    """`a,b` (the kit's output) -> ["a", "b"]; blanks dropped, order kept."""
    out = []
    for t in (text or "").split(","):
        t = t.strip()
        if t and t not in out:
            out.append(t)
    return out


def current_tags(answer):
    """IPublishedFileService/GetDetails -> the item's tags."""
    details = (answer.get("response") or {}).get("publishedfiledetails") or []
    if not details:
        raise Failed("Steam answered no details for the item")
    item = details[0]
    if item.get("result") not in (None, 1):
        raise Failed(f"Steam answered result {item.get('result')} for the item "
                     "(9: not found, or not this key's app)")
    return [t.get("tag") for t in item.get("tags") or [] if t.get("tag")]


def plan(have, want):
    """(add, remove): what makes `have`'s kit tags equal `want`, leaving
    every tag outside the kit's prefixes as it is."""
    add = [t for t in want if t not in have]
    remove = [t for t in have if t.startswith(PREFIXES) and t not in want]
    return add, remove


def update_body(key, app, item, add, remove):
    body = {"key": key, "appid": app, "publishedfileid": item}
    for i, t in enumerate(add):
        body[f"add_tags[{i}]"] = t
    for i, t in enumerate(remove):
        body[f"remove_tags[{i}]"] = t
    return body


def scrub(text, key):
    text = str(text)
    if key:
        for form in {key, urllib.parse.quote(key), urllib.parse.quote_plus(key)}:
            text = text.replace(form, "***")
    return text


def ask(url, key, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "achievehaus-workshop"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise Failed(scrub(f"{urllib.parse.urlsplit(url).path}: HTTP {e.code}"
                           + (" (the key was refused, or is not this app's)"
                              if e.code in (401, 403) else ""), key)) from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise Failed(scrub(f"{urllib.parse.urlsplit(url).path}: {e}", key)) from None


def run(env, out=print, fetch=None):
    fetch = fetch or ask
    want = parse_list(env.get("TAGS"))
    item = (env.get("ITEM_ID") or "").strip()
    app = (env.get("APP_ID") or "").strip()
    key = (env.get("KEY") or "").strip()
    if not item.isdigit() or not app.isdigit():
        raise Failed("ITEM_ID and APP_ID are numbers")
    if not want:
        out("no tags to set")
        return 0
    if not key:
        out("::warning::the item's Workshop tags were not set: no STEAM_TAGS_KEY "
            f"(a publisher Web API key). The tags: {', '.join(want)}")
        return 0
    if env.get("DRY_RUN"):
        out(f"dry run: would read item {item}'s tags, then add {want} "
            "and remove any other kit tag")
        return 0
    q = urllib.parse.urlencode({"key": key, "publishedfileids[0]": item, "includetags": "true",
                                "appid": app})
    have = current_tags(fetch(f"{PARTNER}/IPublishedFileService/GetDetails/v1/?{q}", key))
    add, remove = plan(have, want)
    if not add and not remove:
        out(f"the item's tags are already {', '.join(want)}")
        return 0
    body = urllib.parse.urlencode(update_body(key, app, item, add, remove)).encode()
    fetch(f"{PARTNER}/IPublishedFileService/UpdateTags/v1/", key, body)
    out(f"tags: added {add or 'none'}, removed {remove or 'none'}")
    return 0


def main(env=None):
    env = os.environ if env is None else env
    try:
        return run(env)
    except Failed as e:
        print(f"::error::the content was uploaded, but its tags were not set: "
              f"{scrub(e, env.get('KEY', ''))}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

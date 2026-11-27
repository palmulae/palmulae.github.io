#!/usr/bin/env python3
"""Build the Palmulae website.

Reads the words in site/site.json and site/businesses.json, fills in the templates in
site/templates, copies site/static, and writes the finished site to docs/, the folder
GitHub Pages serves. Uses only the Python standard library.

  python3 build.py                      build docs/
  python3 build.py --check              build docs/, then check every page, link and file
  python3 build.py --preview DIR        build a copy to open on a computer: links end in
                                        index.html and a note says it isn't live
  python3 build.py --preview DIR --example
                                        the same, with two made-up businesses from
                                        site/examples/businesses.json

Never edit docs/ by hand: each build replaces it.
"""

import argparse
import hashlib
import html
import json
import re
import shutil
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from string import Template
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
TEMPLATES = SITE / "templates"
PARTIALS = TEMPLATES / "partials"
STATIC = SITE / "static"
DOCS = ROOT / "docs"
MARKER = ".palmulae-build"

# Each app or business has one accent color of its own, named here. site.css gives each name two colors,
# --app-<name> for words and lines and --app-<name>-soft for the panels behind them, in light and dark.
ACCENTS = ("mint", "navy", "maroon", "gold")
STATUSES = ("live", "soon", "wip")
# The label on a card and its page while it isn't live.
STATUS_CHIPS = {"soon": "Coming soon", "wip": "In development"}
# Apps come before businesses in the home page's list.
KINDS = ("app", "business")
# Folder names the site already uses, or that would confuse people, so no business gets them.
RESERVED = {
    "404", "admin", "api", "app", "apple-touch-icon", "assets", "cname", "docs", "examples",
    "favicon", "fonts", "index", "mail", "privacy", "robots", "site", "sitemap", "static",
    "terms", "tools", "www",
}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
URL_CHARS_RE = re.compile(r"^[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+$")

BUSINESS_KEYS = {
    "slug": True, "name": True, "line": True, "accent": True, "status": True, "kind": False, "icon": False,
    "preview": False,
    "about": False, "description": False, "url": False, "url_label": False,
    "links": False, "contact": False, "privacy": False, "terms": False, "unlisted": False,
    "image": False, "features": False, "sections": False, "fine_print": False,
    "headline": False, "delivery": False, "status_label": False, "status_note": False,
    "actions": False, "blocks": False,
}
IMAGE_KEYS = {
    "src": True, "src_dark": False, "width": True, "height": True, "alt": True, "caption": False,
    "src_small": False, "src_small_dark": False, "small_width": False, "small_height": False,
}
IMAGE_TYPES = (".webp", ".png", ".jpg", ".jpeg", ".avif")
IMAGE_PATH_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*(?:/[a-z0-9][a-z0-9._-]*)*$")
# A picture's "src_small" versions are shown on screens this wide or narrower.
SMALL_SCREEN = 600
# Small labels that say whether something works yet, or what a requirement is. Each draws as a tag
# whose CSS class is its key (tag-now, tag-progress, ...). The second text is what a legend says beside it.
TAGS = {
    "now": ("Working now", "in the prototype today"),
    "progress": ("In progress", "being built and tested"),
    "planned": ("Planned", "not built yet"),
    "required": ("Required", "needed to run it"),
    "optional": ("Optional", "only if you want it"),
    "provisional": ("Provisional", "may change before release"),
    "built": ("Built in", "how the software works"),
    "setup": ("Prototype setup", "the developer's own setup"),
}
ACTION_STYLES = ("primary", "secondary")
# The kinds of block an app's page can carry after its opening, and each kind's own fields.
BLOCK_COMMON = {"kind": True, "heading": True, "id": False, "title": False, "intro": False, "legend": False, "note": False}
BLOCK_KINDS = {
    "figure": {"image": True, "notes": False, "more": False},
    "cards": {"items": True},
    "steps": {"items": True},
    "rows": {"items": True, "cols": False},
    "flow": {"items": True},
    "prose": {"paragraphs": True},
}
ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
PRIVACY_KEYS = {
    "updated": True, "intro": True, "collects": True, "uses": True, "shares": True,
    "keeps": True, "choices": True, "extra": False,
}
TERMS_KEYS = {"updated": True, "paragraphs": True, "sections": False}

PREVIEW_NOTE = (
    '<p>Preview, not live. {examples}</p>'
    '<details><summary>The picture shown when someone shares a link to the site</summary>'
    '<img src="{og}" alt="{alt}" width="1200" height="630" loading="lazy"></details>'
)
PREVIEW_EXAMPLES = (
    "Example App and Example Studio are made up, to show how an app and a business will look. "
    "On the real site, the list of projects shows only real ones, and stays hidden until there is one. "
)


class BuildError(Exception):
    pass


def esc(text):
    return html.escape(str(text), quote=True)


# ---------------------------------------------------------------- checking the words

def need_str(obj, key, where, required=True):
    value = obj.get(key)
    if value is None:
        if required:
            raise BuildError(f"{where}: '{key}' is missing.")
        return None
    if not isinstance(value, str) or not value.strip():
        raise BuildError(f"{where}: '{key}' should be some text in quotes.")
    return value.strip()


def need_list_of_str(obj, key, where, required=True, allow_str=False):
    value = obj.get(key)
    if value is None:
        if required:
            raise BuildError(f"{where}: '{key}' is missing.")
        return None
    if allow_str and isinstance(value, str) and value.strip():
        return value.strip()
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
        kind = "some text, or a list of texts," if allow_str else "a list of texts"
        raise BuildError(f"{where}: '{key}' should be {kind} like [\"First.\", \"Second.\"].")
    return [v.strip() for v in value]


def check_keys(obj, allowed, where):
    if not isinstance(obj, dict):
        raise BuildError(f"{where}: should be a set of fields in curly brackets.")
    unknown = sorted(set(obj) - set(allowed))
    if unknown:
        raise BuildError(f"{where}: unknown field(s) {', '.join(unknown)}. Allowed: {', '.join(allowed)}.")
    for key, required in allowed.items():
        if required and key not in obj:
            raise BuildError(f"{where}: '{key}' is missing.")


def check_url(url, where):
    """Allow https web addresses and mailto email links only."""
    if not URL_CHARS_RE.match(url):
        raise BuildError(f"{where}: '{url}' has characters a web address can't have.")
    if url.startswith("mailto:"):
        if not EMAIL_RE.match(url[len("mailto:"):]):
            raise BuildError(f"{where}: '{url}' isn't a valid email link.")
        return url
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc or "@" in parts.netloc:
        raise BuildError(f"{where}: '{url}' should be a full https:// web address.")
    return url


def check_email(value, where):
    if not EMAIL_RE.match(value):
        raise BuildError(f"{where}: '{value}' isn't a valid email address.")
    return value


APOSTROPHE_RE = re.compile(r"(?<=[A-Za-z])'(?=[A-Za-z])|(?<=s)'(?=\s|$)")


def words(text):
    """Escape text for HTML, with typographic apostrophes (it’s, Example’s, visitors’)."""
    return esc(APOSTROPHE_RE.sub("\u2019", text))


def inline(text, where):
    """Escape text for HTML, turning [words](https://...) into links."""
    out, pos = [], 0
    for m in LINK_RE.finditer(text):
        out.append(words(text[pos:m.start()]))
        url = check_url(m.group(2), where)
        out.append(f'<a href="{esc(url)}">{words(m.group(1))}</a>')
        pos = m.end()
    out.append(words(text[pos:]))
    return "".join(out)


def paragraphs(items, where, indent="    "):
    if isinstance(items, str):
        items = [items]
    return "\n".join(f"{indent}<p>{inline(p, where)}</p>" for p in items)


def block(value, where, indent="    "):
    """One text becomes a paragraph; a list becomes bullet points."""
    if isinstance(value, str):
        return f"{indent}<p>{inline(value, where)}</p>"
    items = "\n".join(f"{indent}  <li>{inline(v, where)}</li>" for v in value)
    return f"{indent}<ul>\n{items}\n{indent}</ul>"


def sections(items, where, key):
    if items is None:
        return ""
    if not isinstance(items, list):
        raise BuildError(f"{where}: '{key}' should be a list of {{\"heading\": ..., \"paragraphs\": [...]}}.")
    out = []
    for n, sec in enumerate(items, 1):
        w = f"{where}, {key} {n}"
        check_keys(sec, {"heading": True, "paragraphs": True}, w)
        out.append(f"    <h2>{inline(need_str(sec, 'heading', w), w)}</h2>")
        out.append(paragraphs(need_list_of_str(sec, "paragraphs", w), w))
    return "\n".join(out)


def shown(path):
    return path.relative_to(ROOT) if path.is_relative_to(ROOT) else path


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise BuildError(f"{shown(path)}: not valid JSON (line {err.lineno}, column {err.colno}): {err.msg}.")


SITE_KEYS = {
    "name": True, "domain": True, "email": True, "description": True, "headline": True, "lede": True,
    "projects_heading": True, "projects_intro": False, "copyright_since": True, "privacy_updated": True,
    "terms_updated": True, "og_image_alt": True,
}


def load_site():
    data = load_json(SITE / "site.json")
    where = "site/site.json"
    check_keys(data, SITE_KEYS, where)
    site = {k: need_str(data, k, where, required=required) for k, required in SITE_KEYS.items()
            if k != "copyright_since"}
    check_email(site["email"], where)
    if not re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", site["domain"]):
        raise BuildError(f"{where}: 'domain' should look like palmulae.com, with no https:// or slashes.")
    since = data.get("copyright_since")
    if not isinstance(since, int) or not 2000 <= since <= 2100:
        raise BuildError(f"{where}: 'copyright_since' should be a year, like 2026.")
    site["copyright_since"] = since
    site["base"] = f"https://{site['domain']}/"
    return site


def load_businesses(path, site):
    data = load_json(path)
    name = shown(path)
    if not isinstance(data, list):
        raise BuildError(f"{name}: should be a list in square brackets, [] when there are none.")
    seen, out = set(), []
    for n, raw in enumerate(data, 1):
        where = f"{name}, business {n}"
        check_keys(raw, BUSINESS_KEYS, where)
        b = {"slug": need_str(raw, "slug", where)}
        where = f"{name}, business {n} ({b['slug']})"
        if not SLUG_RE.match(b["slug"]) or b["slug"] in RESERVED:
            raise BuildError(f"{where}: 'slug' is the page address (palmulae.com/<slug>/). Use lowercase letters, "
                             f"numbers and hyphens, and none of: {', '.join(sorted(RESERVED))}.")
        if b["slug"] in seen:
            raise BuildError(f"{where}: another business already uses this slug.")
        seen.add(b["slug"])
        b["name"] = need_str(raw, "name", where)
        b["line"] = need_str(raw, "line", where)
        b["description"] = need_str(raw, "description", where, required=False) or b["line"]
        b["accent"] = need_str(raw, "accent", where)
        if b["accent"] not in ACCENTS:
            raise BuildError(f"{where}: 'accent' should be one of {', '.join(ACCENTS)}: its own color, "
                             f"on its card and its page.")
        b["icon"] = need_str(raw, "icon", where, required=False)
        if b["icon"] is not None and (not IMAGE_PATH_RE.match(b["icon"]) or not b["icon"].endswith(".svg")):
            raise BuildError(f"{where}: 'icon' should name a square SVG picture in site/static/assets/, like "
                             f"\"{b['slug']}/icon.svg\". Without one, its card shows its first letter.")
        b["status"] = need_str(raw, "status", where)
        if b["status"] not in STATUSES:
            raise BuildError(f"{where}: 'status' should be \"live\", \"soon\" or \"wip\".")
        b["kind"] = raw.get("kind", "business")
        if b["kind"] not in KINDS:
            raise BuildError(f"{where}: 'kind' should be \"app\" or \"business\".")
        b["about"] = need_list_of_str(raw, "about", where, required=False, allow_str=True) or []
        b["url"] = need_str(raw, "url", where, required=False)
        if b["url"]:
            check_url(b["url"], f"{where}, url")
            if b["url"].startswith("mailto:"):
                raise BuildError(f"{where}: 'url' should be a web address. Put email in 'contact'.")
        b["url_label"] = need_str(raw, "url_label", where, required=False) or f"Visit {b['name']}"
        links = raw.get("links") or []
        if not isinstance(links, list):
            raise BuildError(f"{where}: 'links' should be a list of {{\"label\": ..., \"url\": ...}}.")
        b["links"] = []
        for k, link in enumerate(links, 1):
            w = f"{where}, link {k}"
            check_keys(link, {"label": True, "url": True}, w)
            b["links"].append((need_str(link, "label", w), check_url(need_str(link, "url", w), w)))
        b["contact"] = check_email(need_str(raw, "contact", where, required=False) or site["email"], f"{where}, contact")
        b["unlisted"] = raw.get("unlisted", False)
        if not isinstance(b["unlisted"], bool):
            raise BuildError(f"{where}: 'unlisted' should be true or false, without quotes.")
        b["privacy"] = raw.get("privacy")
        if b["privacy"] is not None:
            w = f"{where}, privacy"
            check_keys(b["privacy"], PRIVACY_KEYS, w)
            p = b["privacy"]
            for key in ("updated", "intro", "keeps"):
                need_str(p, key, w)
            for key in ("collects", "uses", "shares", "choices"):
                need_list_of_str(p, key, w, allow_str=True)
        b["terms"] = raw.get("terms")
        if b["terms"] is not None:
            w = f"{where}, terms"
            check_keys(b["terms"], TERMS_KEYS, w)
            need_str(b["terms"], "updated", w)
            need_list_of_str(b["terms"], "paragraphs", w)
        b["image"] = load_image(raw.get("image"), f"{where}, image", b["slug"])
        b["preview"] = load_image(raw.get("preview"), f"{where}, preview", b["slug"])
        b["features"] = load_features(raw.get("features"), where)
        b["sections"] = load_sections(raw.get("sections"), where)
        b["fine_print"] = need_str(raw, "fine_print", where, required=False)
        b["headline"] = need_str(raw, "headline", where, required=False)
        b["delivery"] = need_str(raw, "delivery", where, required=False)
        b["status_label"] = need_str(raw, "status_label", where, required=False)
        b["status_note"] = need_str(raw, "status_note", where, required=False)
        b["blocks"] = load_blocks(raw.get("blocks"), where, b["slug"])
        b["actions"] = load_actions(raw.get("actions"), where, {blk["id"] for blk in b["blocks"]})
        out.append(b)
    return out


def load_image(img, where, slug):
    """A picture for the page, from site/static/assets/, with an optional dark-mode version."""
    if img is None:
        return None
    check_keys(img, IMAGE_KEYS, where)
    out = {}
    for key in ("src", "src_dark", "src_small", "src_small_dark"):
        path = need_str(img, key, where, required=key == "src")
        if path is None:
            continue
        if not IMAGE_PATH_RE.match(path) or not path.endswith(IMAGE_TYPES) or not (STATIC / "assets" / path).is_file():
            raise BuildError(f"{where}: '{key}' should name a picture in site/static/assets/, like "
                             f"\"{slug}/screen.webp\" (one of {', '.join(IMAGE_TYPES)}).")
        out[key] = path
    if "src_small_dark" in out and "src_small" not in out:
        raise BuildError(f"{where}: 'src_small_dark' needs a 'src_small' beside it.")
    sizes = ("width", "height") + (("small_width", "small_height") if "src_small" in out else ())
    for key in sizes:
        value = img.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 10000:
            raise BuildError(f"{where}: '{key}' should be the picture's {key.replace('_', ' ')} in pixels, "
                             f"a whole number without quotes.")
        out[key] = value
    for key in ("small_width", "small_height"):
        if key in img and key not in out:
            raise BuildError(f"{where}: '{key}' only goes with a 'src_small' picture.")
    out["alt"] = need_str(img, "alt", where)
    out["caption"] = need_str(img, "caption", where, required=False)
    return out


def icon_names():
    return sorted(p.stem[len("icon-"):] for p in PARTIALS.glob("icon-*.svg"))


def load_tag(obj, where):
    tag = need_str(obj, "tag", where, required=False)
    if tag is not None and tag not in TAGS:
        raise BuildError(f"{where}: 'tag' should be one of {', '.join(TAGS)}.")
    return tag


def load_list(value, where, key, shape):
    if not isinstance(value, list) or not value:
        raise BuildError(f"{where}: '{key}' should be a list of {shape}.")
    return value


def load_actions(items, where, ids):
    """Buttons under an app's opening: [{"label", "href", "style"}]. An href is a web address, an email
    link, or "#id" for one of the page's own blocks."""
    if items is None:
        return []
    shape = '{"label": ..., "href": ..., "style": "primary" or "secondary"}'
    out = []
    for n, item in enumerate(load_list(items, where, "actions", shape), 1):
        w = f"{where}, actions {n}"
        check_keys(item, {"label": True, "href": True, "style": False}, w)
        href = need_str(item, "href", w)
        if href.startswith("#"):
            if href[1:] not in ids:
                known = ", ".join("#" + i for i in sorted(ids)) or "none yet"
                raise BuildError(f"{w}: '{href}' should be the id of one of this page's blocks ({known}).")
        else:
            check_url(href, w)
        style = need_str(item, "style", w, required=False) or "secondary"
        if style not in ACTION_STYLES:
            raise BuildError(f"{w}: 'style' should be \"primary\" or \"secondary\".")
        out.append({"label": need_str(item, "label", w), "href": href, "style": style})
    return out


def load_blocks(items, where, slug):
    """The blocks of an app's page, in order, each a titled section of one kind (see BLOCK_KINDS)."""
    if items is None:
        return []
    out, ids = [], set()
    for n, raw in enumerate(load_list(items, where, "blocks", '{"kind": ..., "heading": ...}'), 1):
        w = f"{where}, blocks {n}"
        if not isinstance(raw, dict):
            raise BuildError(f"{w}: should be a set of fields in curly brackets.")
        kind = raw.get("kind")
        if kind not in BLOCK_KINDS:
            raise BuildError(f"{w}: 'kind' should be one of {', '.join(BLOCK_KINDS)}.")
        check_keys(raw, {**BLOCK_COMMON, **BLOCK_KINDS[kind]}, w)
        blk = {"kind": kind, "heading": need_str(raw, "heading", w)}
        blk["id"] = need_str(raw, "id", w, required=False) or anchor(slug, blk["heading"])
        if not ID_RE.match(blk["id"]):
            raise BuildError(f"{w}: 'id' should start with a letter and hold only lowercase letters, numbers and hyphens.")
        if blk["id"] in ids:
            raise BuildError(f"{w}: another block already has the id '{blk['id']}'.")
        ids.add(blk["id"])
        blk["title"] = need_str(raw, "title", w, required=False)
        blk["intro"] = need_list_of_str(raw, "intro", w, required=False, allow_str=True)
        blk["note"] = need_list_of_str(raw, "note", w, required=False, allow_str=True)
        legend = raw.get("legend")
        if legend is not None and (not isinstance(legend, list) or not legend or not all(t in TAGS for t in legend)):
            raise BuildError(f"{w}: 'legend' should be a list of tags from {', '.join(TAGS)}.")
        blk["legend"] = legend or []
        loader = globals()["load_block_" + kind]
        loader(raw, blk, w, slug)
        out.append(blk)
    return out


def load_block_figure(raw, blk, w, slug):
    blk["image"] = load_image(raw["image"], f"{w}, image", slug)
    blk["notes"] = []
    if raw.get("notes") is not None:
        for k, note in enumerate(load_list(raw["notes"], w, "notes", '{"title": ..., "text": ..., "tag": ...}'), 1):
            wn = f"{w}, notes {k}"
            check_keys(note, {"title": True, "text": True, "tag": False}, wn)
            blk["notes"].append({"title": need_str(note, "title", wn), "text": need_str(note, "text", wn),
                                 "tag": load_tag(note, wn)})
    blk["more"] = None
    if raw.get("more") is not None:
        wm = f"{w}, more"
        check_keys(raw["more"], {"summary": True, "image": True}, wm)
        blk["more"] = {"summary": need_str(raw["more"], "summary", wm),
                       "image": load_image(raw["more"]["image"], f"{wm}, image", slug)}


def load_block_cards(raw, blk, w, slug):
    icons = icon_names()
    blk["items"] = []
    shape = '{"icon": ..., "title": ..., "text": ..., "tag": ..., "points": [...]}'
    for k, item in enumerate(load_list(raw["items"], w, "items", shape), 1):
        wi = f"{w}, item {k}"
        check_keys(item, {"icon": False, "title": True, "text": False, "tag": False, "points": False}, wi)
        icon = need_str(item, "icon", wi, required=False)
        if icon is not None and icon not in icons:
            raise BuildError(f"{wi}: 'icon' should be one of {', '.join(icons)}.")
        points = []
        if item.get("points") is not None:
            for j, point in enumerate(load_list(item["points"], wi, "points", 'texts, or {"text": ..., "tag": ...}'), 1):
                wp = f"{wi}, point {j}"
                if isinstance(point, str):
                    point = {"text": point}
                check_keys(point, {"text": True, "tag": False}, wp)
                points.append({"text": need_str(point, "text", wp), "tag": load_tag(point, wp)})
        blk["items"].append({"icon": icon, "title": need_str(item, "title", wi),
                             "text": need_str(item, "text", wi, required=False), "tag": load_tag(item, wi),
                             "points": points})


def load_block_steps(raw, blk, w, slug):
    blk["items"] = load_titled(raw["items"], w)


def load_block_rows(raw, blk, w, slug):
    blk["items"] = load_titled(raw["items"], w)
    cols = raw.get("cols", 1)
    if cols not in (1, 2) or isinstance(cols, bool):
        raise BuildError(f"{w}: 'cols' should be 1 or 2, without quotes.")
    blk["cols"] = cols


def load_titled(items, w):
    out = []
    for k, item in enumerate(load_list(items, w, "items", '{"title": ..., "text": ..., "tag": ...}'), 1):
        wi = f"{w}, item {k}"
        check_keys(item, {"title": True, "text": True, "tag": False}, wi)
        out.append({"title": need_str(item, "title", wi), "text": need_str(item, "text", wi), "tag": load_tag(item, wi)})
    return out


def load_block_flow(raw, blk, w, slug):
    """Boxes in a row with an arrow between each two: [{"title", "items": [...], "via", "style"}].
    "via" is the label on the arrow that leads into a box; "style" is "home" or "optional"."""
    blk["items"] = []
    shape = '{"title": ..., "items": [...], "via": ..., "style": ...}'
    for k, box in enumerate(load_list(raw["items"], w, "items", shape), 1):
        wb = f"{w}, item {k}"
        check_keys(box, {"title": True, "items": True, "via": False, "style": False}, wb)
        via = need_str(box, "via", wb, required=False)
        if k == 1 and via:
            raise BuildError(f"{wb}: the first box has no arrow leading into it, so it takes no 'via'.")
        style = need_str(box, "style", wb, required=False)
        if style not in (None, "home", "optional"):
            raise BuildError(f"{wb}: 'style' should be \"home\" or \"optional\".")
        blk["items"].append({"title": need_str(box, "title", wb), "items": need_list_of_str(box, "items", wb),
                             "via": via, "style": style})


def load_block_prose(raw, blk, w, slug):
    blk["paragraphs"] = need_list_of_str(raw, "paragraphs", w)


def load_features(groups, where):
    """Groups of short cards, each with a heading: [{"heading", "items": [{"icon", "title", "text"}]}]."""
    if groups is None:
        return []
    shape = "a list of {\"heading\": ..., \"items\": [{\"icon\": ..., \"title\": ..., \"text\": ...}]}"
    if not isinstance(groups, list):
        raise BuildError(f"{where}: 'features' should be {shape}.")
    icons = sorted(p.stem[len("icon-"):] for p in PARTIALS.glob("icon-*.svg"))
    out = []
    for n, group in enumerate(groups, 1):
        w = f"{where}, features {n}"
        check_keys(group, {"heading": True, "items": True}, w)
        items = group["items"]
        if not isinstance(items, list) or not items:
            raise BuildError(f"{w}: 'items' should be a list of {{\"icon\": ..., \"title\": ..., \"text\": ...}}.")
        cards = []
        for k, item in enumerate(items, 1):
            wi = f"{w}, item {k}"
            check_keys(item, {"icon": False, "title": True, "text": True}, wi)
            icon = need_str(item, "icon", wi, required=False)
            if icon is not None and icon not in icons:
                raise BuildError(f"{wi}: 'icon' should be one of {', '.join(icons)}.")
            cards.append({"icon": icon, "title": need_str(item, "title", wi), "text": need_str(item, "text", wi)})
        out.append({"heading": need_str(group, "heading", w), "items": cards})
    return out


def load_sections(items, where):
    """Short titled sections after the cards: [{"heading", "paragraphs": [...]}]."""
    if items is None:
        return []
    if not isinstance(items, list):
        raise BuildError(f"{where}: 'sections' should be a list of {{\"heading\": ..., \"paragraphs\": [...]}}.")
    out = []
    for n, sec in enumerate(items, 1):
        w = f"{where}, sections {n}"
        check_keys(sec, {"heading": True, "paragraphs": True}, w)
        out.append({"heading": need_str(sec, "heading", w), "paragraphs": need_list_of_str(sec, "paragraphs", w)})
    return out


def biz_section(b, sec):
    hid = anchor(b["slug"], sec["heading"])
    return (f'  <section class="biz-section" aria-labelledby="{hid}">\n'
            f'    <div class="section-head"><h2 id="{hid}">{words(sec["heading"])}</h2></div>\n'
            f'    <div class="prose biz-prose">\n{paragraphs(sec["paragraphs"], b["slug"], "      ")}\n    </div>\n'
            f'  </section>')


def anchor(*parts):
    """An id for a heading, from words: ("proreta", "What it reads") -> "proreta-what-it-reads"."""
    return "-".join(re.sub(r"[^a-z0-9]+", "-", p.lower()).strip("-") for p in parts)


def tag(key):
    """A small label such as "Working now", or nothing."""
    if not key:
        return ""
    return f'<span class="tag tag-{key}">{esc(TAGS[key][0])}</span>'


def points(items, where):
    """A card's short points, grouped under their tags in the order the tags first appear."""
    if not items:
        return ""
    groups = {}
    for p in items:
        groups.setdefault(p["tag"], []).append(p["text"])
    out = []
    for key, texts in groups.items():
        head = f'<p class="points-head">{tag(key)}</p>' if key else ""
        lis = "".join(f"<li>{inline(t, where)}</li>" for t in texts)
        out.append(f'<div class="points-group">{head}<ul>{lis}</ul></div>')
    return f'<div class="points">{"".join(out)}</div>'



# ---------------------------------------------------------------- building pages

class Links:
    """Makes links relative to the page being written, so the site works on any address.

    The not-found page is the exception: GitHub shows it at whatever address was missing,
    so it links from the site's root instead.
    """

    def __init__(self, here, preview, absolute=False):
        self.here = here
        self.preview = preview
        self.root = "/" if absolute else "../" * here.count("/")

    def to(self, target, fragment=""):
        if target == self.here and fragment:
            return "#" + fragment
        path = self.root + target
        if self.preview and (path == "" or path.endswith("/")):
            path += "index.html"
        if path == "":
            path = "./"
        return path + ("#" + fragment if fragment else "")


class Builder:
    def __init__(self, out, preview=False, example=False):
        self.out = out
        self.preview = preview
        self.site = load_site()
        source = SITE / "examples" / "businesses.json" if example else SITE / "businesses.json"
        self.businesses = load_businesses(source, self.site)
        # Unlisted ones get their pages, but no card on the home page, no place in the sitemap,
        # and a noindex for search engines: reachable only by their address.
        self.listed = [b for b in self.businesses if not b["unlisted"]]
        # The home page's list: apps first, then businesses, each in the order of businesses.json.
        self.projects = sorted(self.listed, key=lambda b: KINDS.index(b["kind"]))
        self.templates = {p.stem: Template(p.read_text(encoding="utf-8")) for p in TEMPLATES.glob("*.html")}
        self.partials = {p.name: p.read_text(encoding="utf-8").strip() for p in PARTIALS.iterdir() if p.is_file()}
        self.pages = []  # (url path, file path, indexable)
        # Browsers may keep the stylesheet for a while (GitHub Pages says 10 minutes), so its link carries a
        # tag made from its contents: a changed stylesheet gets a new address and shows up at once.
        self.css_version = hashlib.sha256((STATIC / "assets" / "site.css").read_bytes()).hexdigest()[:10]
        today = date.today().year
        since = self.site["copyright_since"]
        self.year = str(since) if today <= since else f"{since}–{today}"

    def fill(self, template, /, **values):
        try:
            return self.templates[template].substitute(**values)
        except KeyError as err:
            raise BuildError(f"site/templates/{template}.html uses ${{{err.args[0]}}}, which the build doesn't fill.")

    def part(self, partial, /, **values):
        try:
            return Template(self.partials[partial]).substitute(**values)
        except KeyError as err:
            raise BuildError(f"site/templates/partials/{partial} uses ${{{err.args[0]}}}, which the build doesn't fill.")

    def page(self, here, *, title, description, content, indexable=True, head_extra="", absolute=False):
        """Write one page. `here` is its address: "" for home, "privacy/" or "404.html"."""
        site, links = self.site, Links(here, self.preview, absolute)
        nav = []
        if self.projects:
            nav.append(f'<a href="{links.to("", "projects")}">Projects</a>')
        nav.append(f'<a href="{links.to("", "contact")}">Contact</a>')
        banner = ""
        if self.preview:
            examples = PREVIEW_EXAMPLES if any(b["slug"].startswith("example-") for b in self.businesses) else ""
            note = PREVIEW_NOTE.format(examples=esc(examples), og=esc(links.root + "assets/og-image.png"),
                                       alt=esc(site["og_image_alt"]))
            banner = f'<div class="preview-note" role="note"><div>{note}</div></div>'
        robots = "index, follow" if indexable and not self.preview else "noindex, nofollow"
        doc = self.fill(
            "page",
            title=esc(title), description=esc(description), robots=robots,
            canonical=esc(site["base"] + here), site_name=esc(site["name"]),
            og_image=esc(site["base"] + "assets/og-image.png"), og_image_alt=esc(site["og_image_alt"]),
            root=links.root, css_version=self.css_version, head_extra=head_extra,
            galley=self.partials["galley.svg"], banner=banner, home_link=links.to(""), nav_links="".join(nav), content=content.rstrip("\n"),
            year=self.year, privacy_link=links.to("privacy/"), terms_link=links.to("terms/"),
        )
        file = here + "index.html" if here == "" or here.endswith("/") else here
        target = self.out / file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(doc, encoding="utf-8")
        self.pages.append((here, file, indexable))
        return links

    # The home page -----------------------------------------------------------------

    def home(self):
        site = self.site
        links = Links("", self.preview)
        projects = ""
        if self.projects:
            cards = [self.project_card(b, links) for b in self.projects]
            intro = f'\n    <p>{inline(site["projects_intro"], "site.json")}</p>' if site["projects_intro"] else ""
            projects = self.part(
                "projects.html", heading=words(site["projects_heading"]), intro=intro,
                layout="one" if len(cards) == 1 else "grid", cards="\n".join(cards))
        content = self.fill(
            "home", headline=inline(site["headline"], "site.json"), lede=inline(site["lede"], "site.json"),
            projects=projects, email=esc(site["email"]))
        base = site["base"]
        data = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "Organization", "@id": base + "#organization", "name": site["name"], "url": base,
                 "email": site["email"], "logo": base + "apple-touch-icon.png"},
                {"@type": "WebSite", "@id": base + "#website", "name": site["name"], "url": base,
                 "publisher": {"@id": base + "#organization"}},
            ],
        }
        ld = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")
        self.page("", title=site["name"], description=site["description"], content=content,
                  head_extra=f'<script type="application/ld+json">\n{ld}\n</script>')

    def app_icon(self, b, links, size):
        """The app's own icon: its SVG picture, or its first letter on a tile of its color."""
        if b["icon"]:
            return (f'<img class="app-icon" src="{esc(links.root + "assets/" + b["icon"])}" width="{size}" '
                    f'height="{size}" alt="">')
        return f'<span class="app-icon app-icon-letter" aria-hidden="true">{esc(b["name"][:1].upper())}</span>'

    def project_card(self, b, links):
        if b["status"] in STATUS_CHIPS:
            stage = STATUS_CHIPS[b["status"]]
        else:
            stage = urlsplit(b["url"]).netloc if b["url"] else f"{self.site['domain']}/{b['slug']}"
        preview = ""
        if b["preview"]:
            preview = (f'      <div class="project-preview">\n'
                       f'{self.picture(b["preview"], links, indent="        ", lazy=True)}\n      </div>')
        return self.part(
            "card.html", accent=b["accent"], icon=self.app_icon(b, links, 48), name=words(b["name"]),
            line=inline(b["line"], b["slug"]), stage=esc(stage), href=links.to(f"{b['slug']}/"),
            preview=preview)

    # Site-wide pages ------------------------------------------------------------------

    def site_pages(self):
        site = self.site
        common = {"site_name": esc(site["name"]), "email": esc(site["email"])}
        self.page("privacy/", title=f"Privacy · {site['name']}",
                  description=f"How the {site['name']} website handles your information.",
                  content=self.fill("privacy", updated=esc(site["privacy_updated"]), **common))
        self.page("terms/", title=f"Terms · {site['name']}",
                  description=f"Terms for using the {site['name']} website.",
                  content=self.fill("terms", updated=esc(site["terms_updated"]), **common))
        absolute = not self.preview
        home_link = "/" if absolute else "index.html"
        self.page("404.html", title=f"Page not found · {site['name']}",
                  description=f"This page isn't on the {site['name']} website.", indexable=False,
                  content=self.fill("404", home_link=home_link, site_name=esc(site["name"])), absolute=absolute)

    # A page for each business, with its own privacy policy and terms if it has them ----------

    def business_pages(self):
        for b in self.businesses:
            here = f"{b['slug']}/"
            links = Links(here, self.preview)
            w = b["slug"]
            head = self.biz_head(b, links)
            about = f'  <div class="prose biz-about">\n{paragraphs(b["about"], w)}\n  </div>' if b["about"] else ""
            delivery = f'  <p class="biz-delivery">{inline(b["delivery"], w)}</p>' if b["delivery"] else ""
            figure = self.biz_figure(b, links)
            blocks = "\n".join(self.biz_block(b, blk, links) for blk in b["blocks"])
            features = "\n".join(self.biz_features(b, group) for group in b["features"])
            secs = "\n".join(biz_section(b, sec) for sec in b["sections"])
            fine = f'  <p class="fine-print">{inline(b["fine_print"], w)}</p>' if b["fine_print"] else ""
            buttons = []
            for a in b["actions"]:
                href = a["href"] if a["href"].startswith("#") else esc(a["href"])
                buttons.append(f'<a class="action action-{a["style"]}" href="{href}">{words(a["label"])}</a>')
            if b["url"]:
                buttons.append(f'<a class="visit" href="{esc(b["url"])}">{esc(b["url_label"])}</a>')
            buttons += [f'<a href="{esc(url)}">{esc(label)}</a>' for label, url in b["links"]]
            link_row = f'  <div class="biz-links">{"".join(buttons)}</div>' if buttons else ""
            legal = []
            if b["privacy"]:
                legal.append(f'<a href="{links.to(here + "privacy/")}">Privacy policy</a>')
            if b["terms"]:
                legal.append(f'<a href="{links.to(here + "terms/")}">Terms of service</a>')
            legal_row = f'  <p class="biz-legal">{"".join(legal)}</p>' if legal else ""
            content = self.fill(
                "business", accent=b["accent"], head=head,
                chip=self.biz_status(b), about=about, delivery=delivery, links=link_row,
                figure=figure, blocks=blocks, features=features, sections=secs, legal=legal_row,
                contact=esc(b["contact"]), fine_print=fine)
            self.page(here, title=f"{b['name']} · {self.site['name']}", description=b["description"], content=content,
                      indexable=not b["unlisted"])
            if b["privacy"]:
                self.business_privacy(b)
            if b["terms"]:
                self.business_terms(b)

    def biz_head(self, b, links):
        """The page's main heading: the app's icon and name, then its line. With a headline, the icon and
        the name sit small above it, and the headline is the big line."""
        w, icon = b["slug"], self.app_icon(b, links, 56)
        if not b["headline"]:
            return (f'  <h1 class="biz-name">{icon}<span>{words(b["name"])}</span></h1>\n'
                    f'  <p class="biz-line">{inline(b["line"], w)}</p>')
        return (f'  <h1 class="biz-title"><span class="biz-kicker">{icon}<span class="app-name">{words(b["name"])}</span>'
                f'<span class="vh">: </span></span><span class="biz-headline">{inline(b["headline"], w)}</span></h1>')

    def biz_status(self, b):
        label = b["status_label"] or STATUS_CHIPS.get(b["status"])
        if not label:
            return ""
        chip = f'<span class="chip">{words(label)}</span>'
        if not b["status_note"]:
            return f"  {chip}"
        return f'  <p class="biz-status">{chip}<span>{inline(b["status_note"], b["slug"])}</span></p>'

    def biz_figure(self, b, links):
        """The page's picture under its opening words, framed like a screen."""
        return self.figure(b["image"], links, b["slug"], indent="  ") if b["image"] else ""

    def figure(self, img, links, w, indent="  ", lazy=False, extra_class=""):
        """A picture framed like a screen, with its caption."""
        caption = f'\n{indent}  <figcaption>{inline(img["caption"], w)}</figcaption>' if img["caption"] else ""
        cls = "shot" + (" " + extra_class if extra_class else "")
        return (f'{indent}<figure class="{cls}">\n{self.picture(img, links, indent + "  ", lazy)}{caption}\n'
                f'{indent}</figure>')

    def picture(self, img, links, indent="", lazy=False):
        """A picture with its dark-mode and small-screen versions, when there are any."""
        root = links.root + "assets/"
        sources = []
        small = f"(max-width: {SMALL_SCREEN}px)"
        if img.get("src_small"):
            size = f' width="{img["small_width"]}" height="{img["small_height"]}"'
            if img.get("src_small_dark"):
                sources.append(f'<source srcset="{esc(root + img["src_small_dark"])}" '
                               f'media="{small} and (prefers-color-scheme: dark)"{size}>')
            sources.append(f'<source srcset="{esc(root + img["src_small"])}" media="{small}"{size}>')
        if img.get("src_dark"):
            sources.append(f'<source srcset="{esc(root + img["src_dark"])}" media="(prefers-color-scheme: dark)">')
        pad = indent + "  "
        sources = "".join(f"{pad}{s}\n" for s in sources)
        loading = ' loading="lazy"' if lazy else ""
        return (f'{indent}<picture>\n{sources}'
                f'{pad}<img src="{esc(root + img["src"])}" width="{img["width"]}" height="{img["height"]}" '
                f'alt="{words(img["alt"])}" decoding="async"{loading}>\n{indent}</picture>')

    # The blocks of an app's page ---------------------------------------------------------

    def biz_block(self, b, blk, links):
        w, bid = b["slug"], blk["id"]
        parts = [f'    <div class="section-head"><h2 id="{bid}-h">{words(blk["heading"])}</h2></div>']
        if blk["title"]:
            parts.append(f'    <p class="block-title">{inline(blk["title"], w)}</p>')
        if blk["intro"]:
            parts.append(f'    <div class="prose block-intro">\n{paragraphs(blk["intro"], w, "      ")}\n    </div>')
        legend = ""
        if blk["legend"]:
            items = "".join(f'<span class="legend-item">{tag(t)}<span>{esc(TAGS[t][1])}</span></span>'
                            for t in blk["legend"])
            legend = f'    <p class="legend">{items}</p>'
        # A picture comes first, so its legend sits under it, beside the notes that carry the tags.
        if legend and blk["kind"] != "figure":
            parts.append(legend)
        parts.append(getattr(self, "block_" + blk["kind"])(b, blk, links, legend))
        if blk["note"]:
            parts.append(f'    <div class="prose block-note">\n{paragraphs(blk["note"], w, "      ")}\n    </div>')
        return (f'  <section class="biz-section block block-{blk["kind"]}" id="{bid}" aria-labelledby="{bid}-h">\n'
                + "\n".join(parts) + "\n  </section>")

    def block_figure(self, b, blk, links, legend=""):
        w = b["slug"]
        out = [self.figure(blk["image"], links, w, indent="    ", extra_class="shot-wide")]
        if legend:
            out.append(legend)
        if blk["notes"]:
            notes = []
            for n, note in enumerate(blk["notes"], 1):
                notes.append(f'      <li class="note"><span class="note-n" aria-hidden="true">{n}</span>'
                             f'<div><h3>{words(note["title"])}</h3><p>{inline(note["text"], w)}</p>'
                             f'{tag(note["tag"])}</div></li>')
            out.append('    <ol class="notes" role="list">\n' + "\n".join(notes) + "\n    </ol>")
        if blk["more"]:
            more = self.figure(blk["more"]["image"], links, w, indent="      ", lazy=True)
            out.append(f'    <details class="more">\n      <summary>{words(blk["more"]["summary"])}</summary>\n'
                       f'{more}\n    </details>')
        return "\n".join(out)

    def block_cards(self, b, blk, links, legend=""):
        w = b["slug"]
        cards = []
        for item in blk["items"]:
            icon = ""
            if item["icon"]:
                icon = f'<span class="feature-icon">{self.partials["icon-" + item["icon"] + ".svg"]}</span>'
            top = f'<p class="feature-tag">{tag(item["tag"])}</p>' if item["tag"] else ""
            text = f'<p>{inline(item["text"], w)}</p>' if item["text"] else ""
            cards.append(f'      <li class="feature">{top}{icon}<h3>{words(item["title"])}</h3>{text}'
                         f'{points(item["points"], w)}</li>')
        cols = 2 if len(cards) in (1, 2, 4) else 3
        return f'    <ul class="features" role="list" style="--cols: {cols}">\n' + "\n".join(cards) + "\n    </ul>"

    def block_steps(self, b, blk, links, legend=""):
        w = b["slug"]
        steps = []
        for n, item in enumerate(blk["items"], 1):
            steps.append(f'      <li class="step"><span class="step-n" aria-hidden="true">{n}</span>'
                         f'<h3>{words(item["title"])}</h3><p>{inline(item["text"], w)}</p>{tag(item["tag"])}</li>')
        return f'    <ol class="steps" role="list" style="--n: {len(steps)}">\n' + "\n".join(steps) + "\n    </ol>"

    def block_rows(self, b, blk, links, legend=""):
        w = b["slug"]
        rows = []
        for item in blk["items"]:
            rows.append(f'      <div class="row"><dt><span class="row-title">{words(item["title"])}</span>'
                        f'{tag(item["tag"])}</dt><dd>{inline(item["text"], w)}</dd></div>')
        return f'    <dl class="rows rows-{blk["cols"]}">\n' + "\n".join(rows) + "\n    </dl>"

    def block_flow(self, b, blk, links, legend=""):
        w = b["slug"]
        out = []
        for box in blk["items"]:
            if box["via"]:
                gate = " flow-arrow-gate" if box["style"] == "optional" else ""
                out.append(f'      <p class="flow-arrow{gate}"><span>{inline(box["via"], w)}</span></p>')
            style = f' flow-box-{box["style"]}' if box["style"] else ""
            items = "".join(f"<li>{inline(i, w)}</li>" for i in box["items"])
            out.append(f'      <div class="flow-box{style}"><h3>{words(box["title"])}</h3><ul>{items}</ul></div>')
        return '    <div class="flow">\n' + "\n".join(out) + "\n    </div>"

    def block_prose(self, b, blk, links, legend=""):
        return f'    <div class="prose biz-prose">\n{paragraphs(blk["paragraphs"], b["slug"], "      ")}\n    </div>'

    def biz_features(self, b, group):
        hid = anchor(b["slug"], group["heading"])
        cards = []
        for item in group["items"]:
            icon = ""
            if item["icon"]:
                icon = f'<span class="feature-icon">{self.partials["icon-" + item["icon"] + ".svg"]}</span>'
            cards.append(f'      <li class="feature">{icon}<h3>{words(item["title"])}</h3>'
                         f'<p>{inline(item["text"], b["slug"])}</p></li>')
        cols = 2 if len(cards) in (1, 2, 4) else 3
        return (f'  <section class="biz-section" aria-labelledby="{hid}">\n'
                f'    <div class="section-head"><h2 id="{hid}">{words(group["heading"])}</h2></div>\n'
                f'    <ul class="features" style="--cols: {cols}">\n' + "\n".join(cards) + '\n    </ul>\n  </section>')

    def business_privacy(self, b):
        here = f"{b['slug']}/privacy/"
        links = Links(here, self.preview)
        p, w = b["privacy"], f"{b['slug']} privacy"
        extra = sections(p.get("extra"), w, "extra")
        content = self.fill(
            "business-privacy", business_link=links.to(f"{b['slug']}/"), name=words(b["name"]),
            updated=esc(p["updated"]), intro=inline(p["intro"], w), collects=block(p["collects"], w),
            uses=block(p["uses"], w), shares=block(p["shares"], w), keeps=inline(p["keeps"], w),
            choices=block(p["choices"], w), extra=extra, contact=esc(b["contact"]))
        self.page(here, title=f"Privacy policy · {b['name']}",
                  description=f"How {b['name']} handles your information.", content=content,
                  indexable=not b["unlisted"])

    def business_terms(self, b):
        here = f"{b['slug']}/terms/"
        links = Links(here, self.preview)
        t, w = b["terms"], f"{b['slug']} terms"
        body = paragraphs(t["paragraphs"], w)
        more = sections(t.get("sections"), w, "sections")
        content = self.fill(
            "business-terms", business_link=links.to(f"{b['slug']}/"), name=words(b["name"]),
            updated=esc(t["updated"]), paragraphs=body + ("\n" + more if more else ""), contact=esc(b["contact"]))
        self.page(here, title=f"Terms of service · {b['name']}",
                  description=f"The terms for using {b['name']}.", content=content,
                  indexable=not b["unlisted"])

    # Files for search engines and GitHub ------------------------------------------------

    def extras(self):
        base = self.site["base"]
        if self.preview:
            return
        urls = "\n".join(f"  <url><loc>{esc(base + here)}</loc></url>" for here, _, ok in self.pages if ok)
        (self.out / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{urls}\n</urlset>\n", encoding="utf-8")
        (self.out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {base}sitemap.xml\n", encoding="utf-8")
        (self.out / "CNAME").write_text(self.site["domain"] + "\n", encoding="utf-8")
        (self.out / ".nojekyll").write_text("", encoding="utf-8")

    def preview_fragment(self):
        """The artifact preview shows the home page inside its own frame, without the outer tags."""
        doc = (self.out / "index.html").read_text(encoding="utf-8")
        head = re.search(r"<head>(.*?)</head>", doc, re.S).group(1)
        body = re.search(r"<body>(.*?)</body>", doc, re.S).group(1)
        keep = [line for line in head.splitlines() if line.startswith(("<title>", '<link rel="stylesheet"'))]
        keep.insert(1, '<meta name="claude:viewport-fit-sides" content="cover">')
        (self.out / "fragment.html").write_text("\n".join(keep) + "\n" + body.strip() + "\n", encoding="utf-8")

    def run(self):
        prepare(self.out)
        shutil.copytree(STATIC, self.out, dirs_exist_ok=True)
        self.home()
        self.site_pages()
        self.business_pages()
        self.extras()
        if self.preview:
            self.preview_fragment()


def prepare(out):
    """Empty the output folder, but only if an earlier build made it."""
    if out.exists():
        if not out.is_dir():
            raise BuildError(f"{out} is a file, not a folder.")
        if any(out.iterdir()) and not (out / MARKER).exists():
            raise BuildError(f"{out} has files the build didn't make, so it won't empty it. Pick another folder.")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    # Written first, so a build that stops halfway can still be run again into the same folder.
    (out / MARKER).write_text(
        "Made by build.py. Each build replaces this folder, so edit the files in site/ instead.\n",
        encoding="utf-8")


# ---------------------------------------------------------------- checking the result

class PageReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs, self.ids, self.h1, self.title, self.lang = [], set(), 0, False, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "h1":
            self.h1 += 1
        if tag == "title":
            self.title = True
        if tag == "html":
            self.lang = a.get("lang")
        for key in ("href", "src"):
            if a.get(key) is not None:
                self.refs.append(a[key])
        if a.get("srcset"):
            self.refs += [c.split()[0] for c in a["srcset"].split(",") if c.strip()]
        if tag == "meta" and a.get("property") == "og:image":
            self.refs.append(a.get("content", ""))


def check(out, base, preview):
    problems, external = [], set()
    out = out.resolve()
    pages = sorted(p.resolve() for p in out.rglob("*.html"))
    readers = {}
    for page in pages:
        if page.name == "fragment.html":
            continue
        text = page.read_text(encoding="utf-8")
        reader = PageReader()
        reader.feed(text)
        readers[page] = reader
        rel = page.relative_to(out)
        if "${" in text:
            problems.append(f"{rel}: a ${{...}} was left unfilled.")
        if reader.h1 != 1:
            problems.append(f"{rel}: has {reader.h1} main headings; it should have exactly 1.")
        if not reader.title or reader.lang != "en":
            problems.append(f"{rel}: missing its title or language.")
    for page, reader in readers.items():
        rel = page.relative_to(out)
        for ref in reader.refs:
            if ref.startswith("mailto:"):
                if not EMAIL_RE.match(ref[7:]):
                    problems.append(f"{rel}: bad email link {ref}")
                continue
            if ref.startswith(base):
                ref = "/" + ref[len(base):]
            elif ref.startswith(("https://", "http://")):
                external.add(ref)
                continue
            parts = urlsplit(ref)
            path = unquote(parts.path)
            if not path:
                target = page
            else:
                target = out / path.lstrip("/") if path.startswith("/") else page.parent / path
                if target.is_dir():
                    target = target / "index.html"
            target = target.resolve()
            if target != out and out not in target.parents:
                problems.append(f"{rel}: {ref} points outside the site.")
            elif not target.is_file():
                problems.append(f"{rel}: {ref} doesn't lead to a file.")
            elif parts.fragment and target in readers and parts.fragment not in readers[target].ids:
                problems.append(f"{rel}: {ref} points to a part of a page that doesn't exist.")
    css = out / "assets" / "site.css"
    for ref in re.findall(r'url\("([^"]+)"\)', css.read_text(encoding="utf-8")):
        if not (css.parent / ref).is_file():
            problems.append(f"assets/site.css: {ref} is missing.")
    if not preview:
        for name in ("CNAME", ".nojekyll", "robots.txt", "sitemap.xml", "favicon.ico", "favicon.svg",
                     "apple-touch-icon.png", "assets/og-image.png"):
            if not (out / name).is_file():
                problems.append(f"{name} is missing.")
        sitemap = (out / "sitemap.xml").read_text(encoding="utf-8") if (out / "sitemap.xml").is_file() else ""
        for loc in re.findall(r"<loc>([^<]+)</loc>", sitemap):
            here = loc[len(base):]
            file = out / (here + "index.html" if here == "" or here.endswith("/") else here)
            if not file.is_file():
                problems.append(f"sitemap.xml lists {loc}, which isn't a page.")
    return len(readers), problems, sorted(external)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the Palmulae website into docs/.")
    parser.add_argument("--check", action="store_true", help="check every page, link and file after building")
    parser.add_argument("--preview", metavar="DIR", help="build a copy to open on a computer, into DIR")
    parser.add_argument("--example", action="store_true", help="with --preview: use the made-up example businesses")
    args = parser.parse_args(argv)
    if args.example and not args.preview:
        parser.error("--example only works with --preview, so the made-up businesses never reach docs/.")
    out = Path(args.preview).resolve() if args.preview else DOCS
    try:
        builder = Builder(out, preview=bool(args.preview), example=args.example)
        builder.run()
    except BuildError as err:
        print(f"Build stopped: {err}", file=sys.stderr)
        return 2
    count = len(builder.pages)
    print(f"Built {count} pages into {out}.")
    if args.check:
        checked, problems, external = check(out, builder.site["base"], builder.preview)
        for p in problems:
            print(f"  problem: {p}")
        print(f"Checked {checked} pages: {len(problems)} problems. Links to other sites, not opened: {len(external)}.")
        for url in external:
            print(f"  {url}")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

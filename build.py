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

PALETTE = ("navy", "sage", "maroon", "gold", "white")
STATUSES = ("live", "soon", "wip")
# The label on a card and its page while it isn't live.
STATUS_CHIPS = {"soon": "Coming soon", "wip": "Work in progress"}
# Apps and businesses get separate sections on the home page, in this order. Each kind's section
# id, which is also the start of its heading and intro keys in site.json.
KINDS = {"app": "apps", "business": "businesses"}
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
    "slug": True, "name": True, "line": True, "colors": True, "status": True, "kind": False,
    "about": False, "description": False, "url": False, "url_label": False,
    "links": False, "contact": False, "privacy": False, "terms": False, "unlisted": False,
    "image": False, "features": False, "sections": False, "fine_print": False,
}
IMAGE_KEYS = {"src": True, "src_dark": False, "width": True, "height": True, "alt": True, "caption": False}
IMAGE_TYPES = (".webp", ".png", ".jpg", ".jpeg", ".avif")
IMAGE_PATH_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*(?:/[a-z0-9][a-z0-9._-]*)*$")
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
    "On the real site, the Apps or Businesses section stays hidden until it has an entry. "
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


def load_site():
    data = load_json(SITE / "site.json")
    where = "site/site.json"
    site = {k: need_str(data, k, where) for k in (
        "name", "domain", "email", "description", "tagline", "lede", "apps_heading", "apps_intro",
        "businesses_heading", "businesses_intro", "privacy_updated", "terms_updated", "og_image_alt")}
    check_email(site["email"], where)
    if not re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", site["domain"]):
        raise BuildError(f"{where}: 'domain' should look like palmulae.com, with no https:// or slashes.")
    entry = data.get("entry")
    check_keys(entry, {"headword": True, "label": True, "definition": True}, f"{where}, entry")
    site["entry"] = {k: need_str(entry, k, f"{where}, entry") for k in ("headword", "label", "definition")}
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
        colors = raw.get("colors")
        if (not isinstance(colors, list) or len(colors) != 2 or colors[0] == colors[1]
                or not all(c in PALETTE for c in colors)):
            raise BuildError(f"{where}: 'colors' should be two different colors from {', '.join(PALETTE)}, "
                             f"like [\"navy\", \"gold\"]: the blade, then its stripe.")
        b["colors"] = colors
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
        b["features"] = load_features(raw.get("features"), where)
        b["sections"] = load_sections(raw.get("sections"), where)
        b["fine_print"] = need_str(raw, "fine_print", where, required=False)
        out.append(b)
    return out


def load_image(img, where, slug):
    """A picture for the page, from site/static/assets/, with an optional dark-mode version."""
    if img is None:
        return None
    check_keys(img, IMAGE_KEYS, where)
    out = {}
    for key in ("src", "src_dark"):
        path = need_str(img, key, where, required=key == "src")
        if path is None:
            continue
        if not IMAGE_PATH_RE.match(path) or not path.endswith(IMAGE_TYPES) or not (STATIC / "assets" / path).is_file():
            raise BuildError(f"{where}: '{key}' should name a picture in site/static/assets/, like "
                             f"\"{slug}/screen.webp\" (one of {', '.join(IMAGE_TYPES)}).")
        out[key] = path
    for key in ("width", "height"):
        value = img.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 10000:
            raise BuildError(f"{where}: '{key}' should be the picture's {key} in pixels, a whole number without quotes.")
        out[key] = value
    out["alt"] = need_str(img, "alt", where)
    out["caption"] = need_str(img, "caption", where, required=False)
    return out


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
        # The home page's sections, apps first, leaving out a kind with nothing listed: (id, entries).
        self.sections = [(sid, [b for b in self.listed if b["kind"] == kind]) for kind, sid in KINDS.items()]
        self.sections = [(sid, items) for sid, items in self.sections if items]
        self.templates = {p.stem: Template(p.read_text(encoding="utf-8")) for p in TEMPLATES.glob("*.html")}
        self.partials = {p.name: p.read_text(encoding="utf-8").strip() for p in PARTIALS.iterdir() if p.is_file()}
        self.pages = []  # (url path, file path, indexable)
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
        for sid, _ in self.sections:
            nav.append(f'<a href="{links.to("", sid)}">{esc(site[sid + "_heading"])}</a>')
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
            root=links.root, head_extra=head_extra, svg_defs=self.partials["blade-defs.svg"],
            banner=banner, home_link=links.to(""), nav_links="".join(nav), content=content.rstrip("\n"),
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
        sections = []
        for sid, items in self.sections:
            cards = []
            for b in items:
                if b["status"] in STATUS_CHIPS:
                    status = f'<span class="chip">{STATUS_CHIPS[b["status"]]}</span>'
                else:
                    where = urlsplit(b["url"]).netloc if b["url"] else f"{site['domain']}/{b['slug']}"
                    status = f'<p class="where">{esc(where)}</p>'
                cards.append(self.part(
                    "card.html", c1=b["colors"][0], c2=b["colors"][1], blade=self.partials["blade.svg"],
                    href=links.to(f"{b['slug']}/"), name=words(b["name"]), line=inline(b["line"], b["slug"]),
                    status=status))
            n = len(items)
            sections.append(self.part(
                "ventures.html", id=sid, heading=words(site[sid + "_heading"]),
                intro=inline(site[sid + "_intro"], "site.json"), cols=2 if n in (1, 2, 4) else 3,
                cards="\n".join(cards)))
        ventures = "\n".join(sections)
        content = self.fill(
            "home", mark=self.partials["mark.svg"], site_name=esc(site["name"]),
            entry_headword=esc(site["entry"]["headword"]), entry_label=esc(site["entry"]["label"]),
            entry_definition=esc(site["entry"]["definition"]), tagline=inline(site["tagline"], "site.json"),
            lede=inline(site["lede"], "site.json"), ventures=ventures, email=esc(site["email"]))
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
            chip = f'  <span class="chip">{STATUS_CHIPS[b["status"]]}</span>' if b["status"] in STATUS_CHIPS else ""
            about = f'  <div class="prose biz-about">\n{paragraphs(b["about"], w)}\n  </div>' if b["about"] else ""
            figure = self.biz_figure(b, links)
            features = "\n".join(self.biz_features(b, group) for group in b["features"])
            secs = "\n".join(biz_section(b, sec) for sec in b["sections"])
            fine = f'  <p class="fine-print">{inline(b["fine_print"], w)}</p>' if b["fine_print"] else ""
            buttons = []
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
                "business", c1=b["colors"][0], c2=b["colors"][1], blade=self.partials["blade.svg"],
                name=words(b["name"]), line=inline(b["line"], w), chip=chip, about=about, links=link_row,
                figure=figure, features=features, sections=secs, legal=legal_row, contact=esc(b["contact"]),
                fine_print=fine)
            self.page(here, title=f"{b['name']} · {self.site['name']}", description=b["description"], content=content,
                      indexable=not b["unlisted"])
            if b["privacy"]:
                self.business_privacy(b)
            if b["terms"]:
                self.business_terms(b)

    def biz_figure(self, b, links):
        """The page's picture, framed like a screen, with a dark-mode version when there is one."""
        img = b["image"]
        if not img:
            return ""
        src = links.root + "assets/" + img["src"]
        dark = ""
        if img.get("src_dark"):
            dark = (f'      <source srcset="{esc(links.root + "assets/" + img["src_dark"])}" '
                    f'media="(prefers-color-scheme: dark)">\n')
        caption = f'\n    <figcaption>{inline(img["caption"], b["slug"])}</figcaption>' if img["caption"] else ""
        return (f'  <figure class="shot">\n    <picture>\n{dark}'
                f'      <img src="{esc(src)}" width="{img["width"]}" height="{img["height"]}" '
                f'alt="{words(img["alt"])}" decoding="async">\n    </picture>{caption}\n  </figure>')

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

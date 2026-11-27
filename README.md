# palmulae.com

The Palmulae website: a home page, privacy and terms pages, and a ready-made page for each
app or business started under Palmulae. It's plain HTML and CSS, made by a small Python
script, and served free by GitHub Pages from the `docs/` folder of this branch.

## What's where

| Path | What it holds |
| --- | --- |
| `site/site.json` | The words on the home page (the headline, the sentence under it and the heading over the list of apps and businesses), the contact address and the dates on the privacy and terms pages. |
| `site/businesses.json` | The apps and businesses, one entry each. The home page lists them as cards in one section, apps first, and leaves the section out while there are none. |
| `site/templates/` | The page layouts. `partials/` holds the galley drawings, the card on the home page and the small icons. |
| `site/static/` | Copied to the site as is: the stylesheet, the fonts with their licenses, the icons and the link-preview picture. |
| `site/examples/businesses.json` | A made-up app and a made-up business, used only for previews. |
| `build.py` | Makes `docs/` from everything above. Python 3.9 or newer, nothing to install. |
| `tools/render-images.js` | Redraws the icons and the link-preview picture. |
| `tools/proreta-walkthrough.html`, `tools/render-walkthrough.js` | Proreta's walkthrough picture, drawn as a page with made-up people, and the script that turns it into the pictures on Proreta's page and card. |
| `tools/fonts/` | Charis SIL, the walkthrough drawing's serif (SIL Open Font License, its text beside it). Only the drawing uses it; the site doesn't. |
| `docs/` | The finished site that GitHub Pages serves. Each build replaces it, so never edit it by hand. |

## Change something

1. Edit the files in `site/`.
2. Run `python3 build.py --check`. It rebuilds `docs/` and checks every page, link and file.
   It stops with a plain message if something in the JSON is off.
3. Commit `site/` and `docs/` together. The live site updates a minute or two after the push.

To look first, build a preview and open its `index.html` in a browser:

```
python3 build.py --preview /tmp/palmulae-preview --example --check
```

`--example` adds the two made-up businesses, so the home page shows more than one card.
A preview has a note at the top and links that work straight from the folder. It never touches `docs/`.

After changing the name, the headline, the sentence under it or the apps on the home page, redraw the
pictures with `node tools/render-images.js` (needs Node and Playwright), then build again.

## Add an app or business

Add an entry to `site/businesses.json`. Only the first five fields are required.

```json
[
  {
    "slug": "harbor",
    "name": "Harbor",
    "line": "One sentence on what it does.",
    "accent": "navy",
    "status": "live",
    "kind": "app",
    "icon": "harbor/icon.svg",
    "preview": {
      "src": "harbor/preview.webp", "src_dark": "harbor/preview-dark.webp", "width": 1280, "height": 950,
      "alt": "What the preview shows."
    },
    "about": ["A paragraph on who it's for.", "Another, if needed."],
    "url": "https://harbor.example.com/",
    "url_label": "Open Harbor",
    "links": [{ "label": "Get it on the App Store", "url": "https://apps.apple.com/..." }],
    "contact": "info@palmulae.com",
    "image": {
      "src": "harbor/screen.webp", "src_dark": "harbor/screen-dark.webp", "width": 1920, "height": 1080,
      "alt": "What the screen shows.", "caption": "A line under the picture."
    },
    "features": [
      { "heading": "What it does", "items": [{ "icon": "mail", "title": "Email", "text": "One line on it." }] }
    ],
    "sections": [{ "heading": "Status", "paragraphs": ["..."] }],
    "fine_print": "Gmail is a trademark of Google LLC.",
    "privacy": {
      "updated": "January 5, 2027",
      "intro": "What this policy covers.",
      "collects": ["...", "..."],
      "uses": ["..."],
      "shares": "...",
      "keeps": "...",
      "choices": ["..."],
      "extra": [{ "heading": "Children", "paragraphs": ["..."] }]
    },
    "terms": {
      "updated": "January 5, 2027",
      "paragraphs": ["..."],
      "sections": [{ "heading": "...", "paragraphs": ["..."] }]
    }
  }
]
```

- `slug` is the page address, `palmulae.com/harbor/`: lowercase letters, numbers and hyphens.
- `accent` is its own color, on its card and its page: `mint`, `navy`, `maroon` or `gold`. Each has a
  color for words and a soft one for panels, in light and dark, at the top of the stylesheet.
- `status` is `live`, `soon` for a "Coming soon" card, or `wip` for an "In development" one.
- `kind` is `app` or `business` (the default). The home page lists apps first.
- `icon` is its own square SVG icon in `site/static/assets/`, shown on its card and beside its name.
  Without one, its card shows its first letter on a tile of its color.
- `preview` is the glimpse of the product on its card on the home page, set on a panel of its color
  and cropped at the right and bottom: a picture like `image` below, without the caption.
- `url` is the business's own site or app, if it has one. Without one, its page here is its home.
- `contact` defaults to the site's address.
- `"unlisted": true` keeps it off the home page and out of the sitemap, and asks search engines not to list
  its pages. They still work at their addresses: for a private tool that a sign-in provider needs pages for.
- `image` puts a screenshot under the opening words. `src` is a picture in `site/static/assets/`
  (`.webp`, `.png`, `.jpg` or `.avif`), `src_dark` an optional one shown to visitors in dark mode,
  `width` and `height` its size in pixels, `alt` what it shows for people who can't see it, and
  `caption` an optional line under it.
- `features` adds groups of cards, each with a `heading` and `items`. A card has a `title`, a line of
  `text` and an optional `icon`: `calendar`, `chip`, `circles`, `contact`, `globe-off`, `home`, `inbox`,
  `key`, `lock`, `mail`, `message`, `network`, `note`, `sparkle` or `stop`. The icons are the site's own
  drawings, in `site/templates/partials/icon-*.svg`; a new file there adds one. Use these, not other
  companies' logos, which need their owners' permission.
- `sections` adds short titled sections after the cards, and `fine_print` a small line at the bottom,
  for trademark notes.
- A page can open with a `headline`, the benefit in a big line, with the icon and name small above it.
  Then `about`, a `delivery` line on how people will get it, `status_label` and `status_note` (where it
  stands, such as "Private prototype" and "Public release planned"), and `actions`: buttons as
  `{ "label": ..., "href": ..., "style": "primary" }`, where `href` may be `#` and the id of a block.
  Keep one `primary` button, the main next step; the rest are plain.
- `blocks` are the titled sections after the opening, in order. Each has a `kind`, a `heading`, and
  optionally an `id`, a big `title`, an `intro`, a `legend` of tags and a `note` under it.
  - `figure`: an `image`, numbered `notes` that match numbers drawn on the picture, and `more`, a
    second picture behind a click (`{ "summary": ..., "image": ... }`). An image can have small-screen
    versions for phones: `src_small`, `src_small_dark`, `small_width` and `small_height`.
  - `cards`: `items` with an `icon`, a `title`, `text` and `points`, short lines grouped by their tags.
  - `steps`: numbered `items`, each a `title` and `text`.
  - `rows`: `items`, each a `title`, `text` and an optional `tag`, in one column or two (`"cols": 2`).
  - `flow`: boxes with arrows between them, each with a `title`, `items`, the `via` label on the arrow
    into it, and a `style`: `home` (outlined) or `optional` (dashed, behind a dashed arrow).
  - `prose`: `paragraphs`.
  Tags say whether something works yet or what a requirement is: `now` (Working now), `progress`
  (In progress), `planned`, `required`, `optional`, `provisional`, `built` (Built in) and `setup`
  (Prototype setup).
- `privacy` and `terms` make `palmulae.com/harbor/privacy/` and `palmulae.com/harbor/terms/`,
  the addresses app stores and sign-in providers ask for. In any `collects`, `uses`, `shares` or
  `choices`, one piece of text makes a paragraph and a list makes bullet points.
- Any text can hold a link written as `[words](https://...)`.

## Hosting

- GitHub Pages publishes this branch's `docs/` folder. `docs/CNAME` names the domain, `palmulae.com`;
  GitHub sends `www.palmulae.com` and `palmulae.github.io` there.
- Limits: a 1 GB site and about 100 GB of visits a month, static pages only. GitHub's terms don't allow
  running an online business on Pages, such as a shop or a paid service. A business like that gets its
  own hosting, and its page here links to it.
- DNS: the bare domain has GitHub's four A records (`185.199.108.153`, `185.199.109.153`,
  `185.199.110.153`, `185.199.111.153`) and `www` is a CNAME to `palmulae.github.io`.
  Leave every other record alone: the email records, the `_github-pages-challenge-palmulae`
  TXT record that keeps the domain verified, and the records for other subdomains.

## Privacy

The site sets no cookies and loads nothing from other companies: the fonts, icons and pictures are
all served from here. If that changes (analytics, a form, an embedded video), update
`site/templates/privacy.html` and `privacy_updated` in `site/site.json` in the same commit.

## Fonts

Cormorant, Instrument Sans and IBM Plex Mono, each under the SIL Open Font License 1.1. The license
files sit next to the fonts in `site/static/assets/fonts/`.

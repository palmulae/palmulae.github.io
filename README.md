# palmulae.com

The Palmulae website: a home page, privacy and terms pages, and a ready-made page for each
app or business started under Palmulae. It's plain HTML and CSS, made by a small Python
script, and served free by GitHub Pages from the `docs/` folder of this branch.

## What's where

| Path | What it holds |
| --- | --- |
| `site/site.json` | The words on the home page (tagline, Latin line, the sentence under them), the contact address and the dates on the privacy and terms pages. |
| `site/businesses.json` | The apps and businesses, one entry each. While it's `[]`, the home page hides that section. |
| `site/templates/` | The page layouts. `partials/` holds the oar drawings and the business card. |
| `site/static/` | Copied to the site as is: the stylesheet, the fonts with their licenses, the icons and the link-preview picture. |
| `site/examples/businesses.json` | Two made-up businesses, used only for previews. |
| `build.py` | Makes `docs/` from everything above. Python 3.9 or newer, nothing to install. |
| `tools/render-images.js` | Redraws the icons and the link-preview picture. |
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

`--example` adds the two made-up businesses, so the business section and pages show.
A preview has a note at the top and links that work straight from the folder. It never touches `docs/`.

After changing the name, the tagline or the Latin line, redraw the pictures with
`node tools/render-images.js` (needs Node and Playwright), then build again.

## Add an app or business

Add an entry to `site/businesses.json`. Only the first five fields are required.

```json
[
  {
    "slug": "harbor",
    "name": "Harbor",
    "line": "One sentence on what it does.",
    "colors": ["navy", "gold"],
    "status": "live",
    "about": ["A paragraph on who it's for.", "Another, if needed."],
    "url": "https://harbor.example.com/",
    "url_label": "Open Harbor",
    "links": [{ "label": "Get it on the App Store", "url": "https://apps.apple.com/..." }],
    "contact": "info@palmulae.com",
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
- `colors` are the blade, then its stripe: two of `navy`, `sage`, `maroon`, `gold`, `white`.
- `status` is `live`, or `soon` for a "Coming soon" card.
- `url` is the business's own site or app, if it has one. Without one, its page here is its home.
- `contact` defaults to the site's address.
- `"unlisted": true` keeps it off the home page and out of the sitemap, and asks search engines not to list
  its pages. They still work at their addresses: for a private tool that a sign-in provider needs pages for.
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

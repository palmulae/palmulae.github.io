// Draws the site's pictures from its own files, so they match the page:
//   site/static/assets/og-image.png   the picture shown when someone shares a link (1200 x 630)
//   site/static/apple-touch-icon.png  the icon for a phone's home screen (180 x 180)
//   site/static/favicon.ico           the browser-tab icon for older browsers (16, 32 and 48)
// The pictures use the site's own stylesheet, fonts and drawings.
// Run it again after changing the name, the tagline, the Latin line or the drawings:
//   node tools/render-images.js
// Needs Node and Playwright with Chromium.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const site = JSON.parse(read('site/site.json'));
const mark = read('site/templates/partials/mark.svg');
const blade = read('site/templates/partials/blade.svg');
const bladeDefs = read('site/templates/partials/blade-defs.svg');
const favicon = read('site/static/favicon.svg');
const css = pathToFileURL(path.join(root, 'site/static/assets/site.css')).href;

const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const page = (style, body) => `<!doctype html><html lang="en"><head><meta charset="utf-8">
<link rel="stylesheet" href="${css}"><style>html, body { margin: 0; } p { margin: 0; } ${style}</style></head>
<body>${bladeDefs}${body}</body></html>`;

// Blades in a rack, painted like the business cards.
const rack = [['navy', 'gold'], ['sage', 'navy'], ['maroon', 'white'], ['gold', 'maroon'], ['navy', 'white']];

const ogHtml = page(`
body { width: 1200px; height: 630px; overflow: hidden; }
.card { position: relative; width: 1200px; height: 630px; padding: 64px 0 0 88px; }
.card .mark { width: 230px; display: block; margin-left: -6px; }
.name { margin-top: 18px; font-family: var(--font-display); font-weight: 500; font-size: 176px; line-height: .82; letter-spacing: -.015em; }
.entry { margin-top: 30px; display: flex; align-items: baseline; gap: 22px; color: var(--ink-soft); }
.hw { font-family: var(--font-mono); font-size: 23px; letter-spacing: .08em; color: var(--ink); }
.pos { font-family: var(--font-display); font-style: italic; font-size: 30px; }
.def { font-size: 25px; }
.line { margin-top: 30px; font-family: var(--font-display); font-style: italic; font-weight: 500; font-size: 58px; line-height: 1.05; }
.rack { position: absolute; right: 72px; top: 92px; display: grid; gap: 16px; }
.rack .blade { width: 290px; }
.rule { position: absolute; left: 88px; right: 88px; bottom: 52px; border-top: 1.5px solid var(--ink); padding-top: 14px;
  font-family: var(--font-mono); font-weight: 500; font-size: 19px; letter-spacing: .16em; text-transform: uppercase; }
`, `<div class="card">
  ${mark}
  <p class="name">${esc(site.name)}</p>
  <p class="entry"><span class="hw">${esc(site.entry.headword)}</span><span class="pos">${esc(site.entry.label)}</span><span class="def">${esc(site.entry.definition)}</span></p>
  <p class="line">${esc(site.tagline)}</p>
  <div class="rack">${rack.map(([a, b]) => `<div style="--c1: var(--blade-${a}); --c2: var(--blade-${b})">${blade}</div>`).join('')}</div>
  <div class="rule">${esc(site.domain)}</div>
</div>`);

const touchHtml = page(`
body { width: 180px; height: 180px; overflow: hidden; background: var(--ink); display: grid; place-items: center; }
body .mark { width: 148px; color: var(--paper); }
body .mark .shaft { stroke-width: 3; }
`, mark);

const iconHtml = size => `<!doctype html><html lang="en"><head><meta charset="utf-8"><style>
html, body { margin: 0; background: transparent; }
svg { display: block; width: ${size}px; height: ${size}px; }
</style></head><body>${favicon}</body></html>`;

// An .ico file is a small header followed by PNG pictures.
function ico(pngs) {
  const header = Buffer.alloc(6 + 16 * pngs.length);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(pngs.length, 4);
  let offset = header.length;
  pngs.forEach(({ size, data }, i) => {
    const at = 6 + 16 * i;
    header.writeUInt8(size >= 256 ? 0 : size, at);
    header.writeUInt8(size >= 256 ? 0 : size, at + 1);
    header.writeUInt16LE(1, at + 4);
    header.writeUInt16LE(32, at + 6);
    header.writeUInt32LE(data.length, at + 8);
    header.writeUInt32LE(offset, at + 12);
    offset += data.length;
  });
  return Buffer.concat([header, ...pngs.map(p => p.data)]);
}

async function shoot(browser, markup, width, height, file, transparent = false) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'palmulae-'));
  const tmp = path.join(dir, 'page.html');
  fs.writeFileSync(tmp, markup);
  // Reduced motion shows the mark at rest, as it ends its stroke.
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, colorScheme: 'light', reducedMotion: 'reduce' });
  const p = await context.newPage();
  await p.goto(pathToFileURL(tmp).href, { waitUntil: 'load' });
  await p.evaluate(() => document.fonts.ready);
  const data = await p.screenshot({ type: 'png', omitBackground: transparent, clip: { x: 0, y: 0, width, height } });
  await context.close();
  fs.rmSync(dir, { recursive: true, force: true });
  if (file) fs.writeFileSync(path.join(root, file), data);
  return data;
}

(async () => {
  const browser = await chromium.launch();
  await shoot(browser, ogHtml, 1200, 630, 'site/static/assets/og-image.png');
  await shoot(browser, touchHtml, 180, 180, 'site/static/apple-touch-icon.png');
  const pngs = [];
  for (const size of [16, 32, 48]) pngs.push({ size, data: await shoot(browser, iconHtml(size), size, size, null, true) });
  fs.writeFileSync(path.join(root, 'site/static/favicon.ico'), ico(pngs));
  await browser.close();
  console.log('Drew og-image.png, apple-touch-icon.png and favicon.ico.');
})().catch(err => { console.error(err); process.exit(1); });

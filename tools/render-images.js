// Draws the site's pictures from its own files, so they match the page:
//   site/static/assets/og-image.png   the picture shown when someone shares a link (1200 x 630)
//   site/static/apple-touch-icon.png  the icon for a phone's home screen (180 x 180)
//   site/static/favicon.ico           the browser-tab icon for older browsers (16, 32 and 48)
// Run it again after changing the name, the tagline or the Latin line in site/site.json:
//   node tools/render-images.js
// Needs Node and Playwright with Chromium.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
const site = JSON.parse(fs.readFileSync(path.join(root, 'site/site.json'), 'utf8'));
const mark = fs.readFileSync(path.join(root, 'site/templates/partials/mark.svg'), 'utf8');
const blade = fs.readFileSync(path.join(root, 'site/templates/partials/blade.svg'), 'utf8');
const bladeDefs = fs.readFileSync(path.join(root, 'site/templates/partials/blade-defs.svg'), 'utf8');
const favicon = fs.readFileSync(path.join(root, 'site/static/favicon.svg'), 'utf8');
const fonts = pathToFileURL(path.join(root, 'site/static/assets/fonts')).href;

const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const base = `
@font-face { font-family: "Cormorant"; font-weight: 300 700; src: url("${fonts}/cormorant.woff2") format("woff2"); }
@font-face { font-family: "Cormorant"; font-style: italic; font-weight: 300 700; src: url("${fonts}/cormorant-italic.woff2") format("woff2"); }
@font-face { font-family: "Instrument Sans"; font-weight: 400 700; src: url("${fonts}/instrument-sans.woff2") format("woff2"); }
@font-face { font-family: "IBM Plex Mono"; font-weight: 400; src: url("${fonts}/ibm-plex-mono-400.woff2") format("woff2"); }
@font-face { font-family: "IBM Plex Mono"; font-weight: 500; src: url("${fonts}/ibm-plex-mono-500.woff2") format("woff2"); }
:root {
  --paper: #F2F5F3; --card: #FBFCFB; --ink: #132326; --ink-soft: #4B5D5F; --accent: #1C5A50;
  --blade-navy: #1E3D5E; --blade-sage: #86AE9C; --blade-maroon: #7B2F3A; --blade-gold: #C29D3F; --blade-white: #FBFCFB;
}
* { box-sizing: border-box; }
html, body { margin: 0; }
.defs { position: absolute; width: 0; height: 0; overflow: hidden; }
p { margin: 0; }
.mark .shaft { stroke: currentColor; stroke-width: 2.4; stroke-linecap: round; }
.mark .blade-shape { fill: currentColor; }
.oar { transform-box: fill-box; transform-origin: 50% 100%; transform: rotate(var(--a)); }
.blade { display: block; overflow: visible; }
.blade .shaft { stroke: var(--ink-soft); stroke-width: 2; stroke-linecap: round; }
.blade .base { fill: var(--c1); }
.blade .stripe { fill: var(--c2); }
.blade .edge { fill: none; stroke: var(--ink); stroke-opacity: .3; stroke-width: .75; }
`;

const rack = [['navy', 'gold'], ['sage', 'navy'], ['maroon', 'white'], ['gold', 'maroon'], ['navy', 'white']];

const ogHtml = `<!doctype html><html lang="en"><head><meta charset="utf-8"><style>${base}
body { width: 1200px; height: 630px; overflow: hidden; background: var(--paper); color: var(--ink); font-family: "Instrument Sans", sans-serif; }
.card { position: relative; width: 1200px; height: 630px; padding: 70px 0 0 88px; }
.mark { width: 128px; height: auto; color: var(--ink); overflow: visible; display: block; }
.name { margin: 26px 0 0; font-family: "Cormorant", serif; font-weight: 500; font-size: 176px; line-height: .82; letter-spacing: -.015em; }
.entry { margin: 30px 0 0; display: flex; align-items: baseline; gap: 22px; color: var(--ink-soft); }
.hw { font-family: "IBM Plex Mono", monospace; font-size: 23px; letter-spacing: .08em; color: var(--ink); }
.pos { font-family: "Cormorant", serif; font-style: italic; font-size: 30px; }
.def { font-size: 25px; }
.tagline { margin: 30px 0 0; font-family: "Cormorant", serif; font-style: italic; font-weight: 500; font-size: 58px; line-height: 1.05; }
.rack { position: absolute; right: 72px; top: 92px; display: grid; gap: 16px; }
.rack .blade { width: 290px; height: auto; }
.rule { position: absolute; left: 88px; right: 88px; bottom: 52px; border-top: 1.5px solid var(--ink); padding-top: 14px;
  display: flex; justify-content: space-between; font-family: "IBM Plex Mono", monospace; font-weight: 500; font-size: 19px; letter-spacing: .16em; text-transform: uppercase; }
</style></head><body>${bladeDefs}
<div class="card">
  ${mark}
  <p class="name">${esc(site.name)}</p>
  <p class="entry"><span class="hw">${esc(site.entry.headword)}</span><span class="pos">${esc(site.entry.label)}</span><span class="def">${esc(site.entry.definition)}</span></p>
  <p class="tagline">${esc(site.tagline)}</p>
  <div class="rack">${rack.map(([a, b]) => `<div style="--c1: var(--blade-${a}); --c2: var(--blade-${b})">${blade}</div>`).join('')}</div>
  <div class="rule"><span>${esc(site.domain)}</span></div>
</div></body></html>`;

const touchHtml = `<!doctype html><html lang="en"><head><meta charset="utf-8"><style>${base}
body { width: 180px; height: 180px; overflow: hidden; background: var(--accent); display: grid; place-items: center; }
.mark { width: 124px; height: auto; color: var(--paper); overflow: visible; display: block; margin-top: -4px; }
.mark .shaft { stroke-width: 3.6; }
</style></head><body>${mark}</body></html>`;

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
    header.writeUInt8(0, at + 2);
    header.writeUInt8(0, at + 3);
    header.writeUInt16LE(1, at + 4);
    header.writeUInt16LE(32, at + 6);
    header.writeUInt32LE(data.length, at + 8);
    header.writeUInt32LE(offset, at + 12);
    offset += data.length;
  });
  return Buffer.concat([header, ...pngs.map(p => p.data)]);
}

async function shoot(browser, markup, width, height, file, transparent = false) {
  const tmp = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'palmulae-')), 'page.html');
  fs.writeFileSync(tmp, markup);
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, colorScheme: 'light' });
  const page = await context.newPage();
  await page.goto(pathToFileURL(tmp).href, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  const data = await page.screenshot({ type: 'png', omitBackground: transparent, clip: { x: 0, y: 0, width, height } });
  await context.close();
  fs.rmSync(path.dirname(tmp), { recursive: true, force: true });
  if (file) fs.writeFileSync(file, data);
  return data;
}

(async () => {
  const browser = await chromium.launch();
  await shoot(browser, ogHtml, 1200, 630, path.join(root, 'site/static/assets/og-image.png'));
  await shoot(browser, touchHtml, 180, 180, path.join(root, 'site/static/apple-touch-icon.png'));
  const pngs = [];
  for (const size of [16, 32, 48]) pngs.push({ size, data: await shoot(browser, iconHtml(size), size, size, null, true) });
  fs.writeFileSync(path.join(root, 'site/static/favicon.ico'), ico(pngs));
  await browser.close();
  console.log('Drew og-image.png, apple-touch-icon.png and favicon.ico.');
})().catch(err => { console.error(err); process.exit(1); });

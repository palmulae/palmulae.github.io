// Draws the site's pictures from its own files, so they match the page:
//   site/static/assets/og-image.png   the picture shown when someone shares a link (1200 x 630)
//   site/static/apple-touch-icon.png  the icon for a phone's home screen (180 x 180)
//   site/static/favicon.ico           the browser-tab icon for older browsers (16, 32 and 48)
// The pictures use the site's own stylesheet, fonts and drawings, and the icons of the apps listed in
// site/businesses.json. Run it again after changing the name, the headline, the line under it, the drawings
// or the listed apps:
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
const galley = read('site/templates/partials/galley.svg');
const favicon = read('site/static/favicon.svg');
const css = pathToFileURL(path.join(root, 'site/static/assets/site.css')).href;
const asset = file => pathToFileURL(path.join(root, 'site/static/assets', file)).href;

const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
// Links written [like this](https://...) in site.json show as their words.
const plain = s => String(s).replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
const page = (style, body) => `<!doctype html><html lang="en"><head><meta charset="utf-8">
<link rel="stylesheet" href="${css}"><style>html, body { margin: 0; } p { margin: 0; } ${style}</style></head>
<body>${body}</body></html>`;

// The apps on the home page, apps before businesses, up to three: each with its icon and name.
const listed = JSON.parse(read('site/businesses.json')).filter(b => !b.unlisted);
const projects = [...listed.filter(b => b.kind === 'app'), ...listed.filter(b => b.kind !== 'app')].slice(0, 3);
const tiles = projects.map(b => `<figure class="app" style="--app: var(--app-${b.accent}); --app-soft: var(--app-${b.accent}-soft)">${
  b.icon ? `<img src="${asset(b.icon)}" alt="">` : `<span class="letter">${esc(b.name[0].toUpperCase())}</span>`
}<figcaption>${esc(b.name)}</figcaption></figure>`).join('');

const ogHtml = page(`
body { width: 1200px; height: 630px; overflow: hidden; }
.card { position: relative; width: 1200px; height: 630px; padding: 60px 88px 0; }
.brand { display: flex; align-items: center; gap: 16px; font-family: var(--font-display); font-weight: 600; font-size: 44px; line-height: 1; }
.brand .galley { width: 64px; height: auto; margin-top: -6px; }
.headline { margin-top: 58px; max-width: 760px; font-family: var(--font-display); font-weight: 500; font-size: 112px; line-height: .93; letter-spacing: -.018em; }
.lede { margin-top: 30px; max-width: 640px; font-size: 27px; line-height: 1.45; color: var(--ink-soft); }
.apps { position: absolute; right: 88px; top: 132px; display: flex; gap: 28px; }
.app { margin: 0; display: grid; justify-items: center; gap: 16px; }
.app img, .app .letter { display: grid; place-items: center; width: 168px; height: 168px; border-radius: 23%; }
.app .letter { background: var(--app-soft); color: var(--app); font-weight: 700; font-size: 84px; }
.app figcaption { font-weight: 600; font-size: 30px; letter-spacing: -.015em; }
.rule { position: absolute; left: 88px; right: 88px; bottom: 50px; border-top: 1.5px solid var(--ink); padding-top: 14px;
  font-family: var(--font-mono); font-weight: 500; font-size: 19px; letter-spacing: .16em; text-transform: uppercase; }
`, `<div class="card">
  <p class="brand">${galley}<span>${esc(site.name)}</span></p>
  <p class="headline">${esc(plain(site.headline))}</p>
  <p class="lede">${esc(plain(site.lede))}</p>
  <div class="apps">${tiles}</div>
  <div class="rule">${esc(site.domain)}</div>
</div>`);

const touchHtml = page(`
body { width: 180px; height: 180px; overflow: hidden; background: var(--ink); display: grid; place-items: center; }
body .mark { --cut: var(--ink); width: 164px; color: var(--paper); margin-top: 6px; }
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

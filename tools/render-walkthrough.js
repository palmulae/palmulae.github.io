// Draws the walkthrough pictures on Proreta's page from tools/proreta-walkthrough.html:
//   site/static/assets/proreta/walkthrough-light.webp, walkthrough-dark.webp              wide screens
//   site/static/assets/proreta/walkthrough-small-light.webp, walkthrough-small-dark.webp  phones
//   site/static/assets/proreta/preview-light.webp, preview-dark.webp                       the home page's card
// Run it again after changing the drawing:
//   node tools/render-walkthrough.js
// It prints each picture's size in pixels. Copy those into Proreta's entry in site/businesses.json: the
// walkthrough's "width" and "height" (wide) and "small_width" and "small_height" (phones), and the preview's.
// Needs Node and Playwright with Chromium.

const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
const drawing = pathToFileURL(path.join(__dirname, 'proreta-walkthrough.html')).href;
const outDir = path.join(root, 'site/static/assets/proreta');

// The drawing's width in CSS pixels; each picture is drawn at twice that, for sharp screens.
const pictures = [
  { name: 'walkthrough', width: 1040 },
  { name: 'walkthrough-small', width: 400 },
  { name: 'preview', width: 640, hash: '#preview' },
];

(async () => {
  const browser = await chromium.launch();
  for (const picture of pictures) {
    for (const scheme of ['light', 'dark']) {
      const context = await browser.newContext({
        viewport: { width: picture.width, height: 800 }, deviceScaleFactor: 2, colorScheme: scheme,
      });
      const page = await context.newPage();
      await page.goto(drawing + (picture.hash || ''));
      await page.evaluate(() => document.fonts.ready);
      const png = await (await page.$('.app')).screenshot({ type: 'png' });
      // Chromium writes WebP from a canvas, so the picture needs no other tool.
      const webp = await page.evaluate(async b64 => {
        const img = new Image();
        img.src = 'data:image/png;base64,' + b64;
        await img.decode();
        const canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        canvas.getContext('2d').drawImage(img, 0, 0);
        return { data: canvas.toDataURL('image/webp', 0.9).split(',')[1], width: img.naturalWidth, height: img.naturalHeight };
      }, png.toString('base64'));
      const file = path.join(outDir, `${picture.name}-${scheme}.webp`);
      fs.writeFileSync(file, Buffer.from(webp.data, 'base64'));
      console.log(`${path.relative(root, file)}  ${webp.width} x ${webp.height}  ${Math.round(fs.statSync(file).size / 1024)} KB`);
      await context.close();
    }
  }
  await browser.close();
})();

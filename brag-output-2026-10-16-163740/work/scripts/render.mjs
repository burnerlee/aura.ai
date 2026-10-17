import { chromium } from '/Users/burnerlee/.npm/_npx/9833c18b2d85bc59/node_modules/playwright-core/index.mjs';
import fs from 'fs'; import path from 'path';
const [mode, outDir, ...rest] = process.argv.slice(2);
fs.mkdirSync(outDir, { recursive: true });
const b = await chromium.launch({ channel: 'chrome', headless: true });
const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
p.on('pageerror', e => console.error('ERR', e.message));
await p.goto('file://' + path.resolve('video.html'));
await p.evaluate(() => window.ready);
const times = mode === 'stills' ? rest.map(Number) : Array.from({ length: Math.round(Number(rest[0]) * 30) }, (_, i) => i / 30);
let i = 0;
for (const t of times) {
  await p.evaluate(t => setTime(t), t);
  const name = mode === 'stills' ? `t${t.toFixed(2)}.png` : `f${String(i).padStart(5, '0')}.jpg`;
  await p.screenshot({ path: `${outDir}/${name}`, ...(mode === 'stills' ? {} : { type: 'jpeg', quality: 93 }) });
  i++;
}
await b.close();

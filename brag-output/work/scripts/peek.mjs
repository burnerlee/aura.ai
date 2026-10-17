import { chromium } from '/Users/burnerlee/.npm/_npx/9833c18b2d85bc59/node_modules/playwright-core/index.mjs';
const b = await chromium.launch({ channel: 'chrome', headless: true });
const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
await p.goto(process.argv[2]); await p.waitForTimeout(3000);
await p.screenshot({ path: process.argv[3] });
console.log(await p.evaluate(()=>document.body.innerText.slice(0,1500)));
await b.close();

import { chromium } from '/Users/burnerlee/.npm/_npx/9833c18b2d85bc59/node_modules/playwright-core/index.mjs';
import fs from 'fs';
const out = process.argv[2];
const b = await chromium.launch({ channel: 'chrome', headless: true });
const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
await p.goto('http://localhost:5174'); await p.waitForTimeout(1500);
// storage persists from no context -> fresh; run chat flow quickly
const opt = async (txt) => { await p.locator('.aura-option-chip', { hasText: txt }).first().click(); await p.waitForTimeout(900); };
await p.waitForTimeout(800);
await opt('AI'); await opt('Deep, thoughtful'); await opt('Less hype');
await p.click('.aura-chat-actions .button-primary'); await p.waitForTimeout(1500);
await p.click('.glass-profile-trigger'); await p.waitForTimeout(800);
await p.evaluate(() => document.querySelector('.resonate-button').click());
await p.waitForTimeout(250);
fs.writeFileSync(`${out}/burst-fly.html`, await p.evaluate(() => document.getElementById('root').innerHTML)); await p.screenshot({ path: `${out}/burst-fly.png` });
await p.waitForTimeout(650);
fs.writeFileSync(`${out}/burst-hit.html`, await p.evaluate(() => document.getElementById('root').innerHTML)); await p.screenshot({ path: `${out}/burst-hit.png` });
await b.close();

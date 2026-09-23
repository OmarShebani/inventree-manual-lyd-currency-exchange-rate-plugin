/* Smoke tests of the shipped UI with a simulated native InvenTree API context. */
import assert from 'node:assert/strict';
import {readFile, mkdir} from 'node:fs/promises';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const source = await readFile(new URL('../shared/static/settings.js', import.meta.url), 'utf8');
const browser = await chromium.launch({headless:true});
const page = await browser.newPage({viewport:{width:1100,height:1000}});
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const moduleURL = 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
const output = process.env.UI_OUTPUT || '/tmp/lyd-ui';
await mkdir(output, {recursive:true});
async function render(individual, fail=false) {
  await page.setContent('<html><body style="font-family:system-ui;margin:24px"><main id="settings"></main></body></html>');
  await page.evaluate(async ({moduleURL, individual, fail}) => {
    const config = {global_currency:'USD', rows:{USD:{mode:'manual', direction:'foreign_to_lyd', value:'10'}}};
    if (individual) for (const code of ['EUR','GBP','CNY']) config.rows[code] = {mode:'auto', via:'USD'};
    let state = {revision:0, config, individual, selected:true, title:'LYD Exchange Rates — ' + (individual ? 'Individual Overrides' : 'Global Only'),
      currencies:['USD','EUR','GBP','CNY','JPY','CAD'].map(code => ({code, name:code})),
      enabled_currencies:['LYD','USD','EUR','GBP','CNY'], snapshot:null, error:null};
    window.calls = [];
    const copy = () => ({data:structuredClone(state)});
    const api = {
      get:async () => {if(fail) throw {response:{data:{detail:'Administrator access required.'}}}; return copy();},
      put:async (url, body) => {window.calls.push(['put', structuredClone(body)]); state.config=structuredClone(body.config); state.revision++; return copy();},
      post:async (url, body) => {window.calls.push(['post', structuredClone(body)]); return copy();}
    };
    const {renderPluginSettings} = await import(moduleURL);
    renderPluginSettings(document.querySelector('#settings'), {context:{endpoint:'/plugin/test/configuration/'}, api});
  }, {moduleURL, individual, fail});
}
try {
  await render(true);
  await page.getByRole('button', {name:'Save settings and refresh',exact:true}).waitFor();
  assert.equal(await page.getByLabel('LYD for 1 USD').inputValue(), '10');
  assert.equal(await page.getByRole('button',{name:'Remove USD',exact:true}).isDisabled(),true);
  await page.getByLabel('Rate direction', {exact:true}).first().selectOption('lyd_to_foreign');
  assert.equal(await page.getByLabel('USD for 1 LYD').inputValue(), '0.1');
  const eur = page.locator('.lyd-box').filter({has:page.locator('strong',{hasText:/^EUR$/})});
  await eur.getByLabel('Mode',{exact:true}).selectOption('manual');
  await page.getByLabel('LYD for 1 EUR').fill('20');
  assert.equal(await page.getByRole('button',{name:'Refresh saved rates',exact:true}).isDisabled(),true);
  await page.getByRole('button',{name:'Remove CNY',exact:true}).click();
  await page.getByLabel('Add an individual currency').selectOption('JPY');
  await page.getByRole('button',{name:'Add currency',exact:true}).click();
  await page.getByRole('button',{name:'Save settings and refresh',exact:true}).click();
  await page.getByRole('status').waitFor();
  const calls = await page.evaluate(() => window.calls);
  assert.equal(calls[0][1].config.rows.EUR.value,'20');
  assert.equal(calls[0][1].config.rows.USD.value,'0.1');
  assert.equal(calls[0][1].config.rows.JPY.via,'USD');
  assert.ok(!calls[0][1].config.rows.CNY);
  assert.equal(calls[1][1].action,'refresh');
  await page.screenshot({path:output+'/individual.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= 390));
  await page.screenshot({path:output+'/individual-mobile.png',fullPage:true});
  await page.setViewportSize({width:1100,height:900});
  await render(false);
  await page.getByLabel('LYD for 1 USD').waitFor();
  assert.equal(await page.getByRole('button',{name:'Add currency',exact:true}).count(),0);
  await page.getByLabel('Global intermediary (required, manual rate only)',{exact:true}).selectOption('EUR');
  assert.equal(await page.getByLabel('LYD for 1 EUR').inputValue(),'');
  await page.getByLabel('LYD for 1 EUR').fill('12');
  await page.getByRole('button',{name:'Save settings and refresh',exact:true}).click();
  await page.getByRole('status').waitFor();
  const global = await page.evaluate(() => window.calls[0][1].config);
  assert.equal(global.global_currency,'EUR');
  assert.deepEqual(Object.keys(global.rows),['EUR']);
  await page.screenshot({path:output+'/global.png',fullPage:true});
  await render(false,true);
  await page.getByRole('alert').waitFor();
  assert.match(await page.getByRole('alert').innerText(),/Administrator access/);
  assert.deepEqual(errors,[]);
  console.log('Browser checks passed: both variants, reciprocal entry, editing, add/remove, saving, mobile layout, errors.');
} finally {await browser.close();}

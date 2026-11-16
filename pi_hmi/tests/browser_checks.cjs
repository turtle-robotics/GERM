/* Real browser, disposable synthetic Flask server; no user profile or hardware. */
const {spawn} = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.GERM_PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const root = path.resolve(__dirname, '../..');
  const output = path.resolve(process.env.GERM_BROWSER_OUTPUT || path.join(root, 'build/m1-browser'));
  fs.mkdirSync(output, {recursive:true});
  const child = spawn(process.env.GERM_TEST_PYTHON || 'python', [path.join(__dirname,'browser_host.py')],
    {cwd:root, env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'}, stdio:['ignore','pipe','pipe']});
  let browser;
  let logs = '';
  child.stderr.on('data', chunk => logs += chunk);
  try {
    const port = await new Promise((resolve,reject) => {
      let text = '';
      const timeout = setTimeout(() => reject(Error('Synthetic server startup timeout')),15000);
      child.on('exit', code => reject(Error('Synthetic server exited: ' + code + ' ' + logs)));
      child.stdout.on('data', chunk => {
        text += chunk;
        if (text.includes('\n')) { clearTimeout(timeout); resolve(JSON.parse(text.split('\n')[0]).port); }
      });
    });
    browser = await chromium.launch({headless:true, executablePath:process.env.GERM_TEST_BROWSER || undefined});
    const page = await browser.newPage({viewport:{width:739,height:447}});
    const errors=[];
    page.on('pageerror', e => errors.push(e.message));
    const base = 'http://127.0.0.1:' + port;
    const state = async () => (await page.request.get(base+'/api/state')).json();
    await page.goto(base+'/controls');
    await page.locator('#boundary-status').filter({hasText:'SIMULATION'}).waitFor();
    await page.locator('[data-command="pump-on"]').click();
    await page.locator('#confirm-dialog[open]').waitFor();
    const before = (await state()).operating_state.last_command;
    await page.locator('#cancel-command').click();
    assert.deepEqual((await state()).operating_state.last_command,before);
    await page.locator('[data-command="pump-on"]').click();
    await page.locator('#confirm-dialog[open]').waitFor();
    const sent = page.waitForResponse(r => r.url().endsWith('/api/pump') && r.request().method()==='POST');
    await page.locator('#accept-command').click();
    const result = await (await sent).json();
    assert.equal(result.accepted,true);
    assert.equal(result.firmware_confirmed,true);
    assert.equal(result.physically_verified,false);
    await page.goto(base+'/maintenance');
    page.once('dialog',dialog => dialog.accept());
    await page.locator('[data-workflow="enter_maintenance"]').click();
    await page.locator('#maintenance-banner').waitFor({state:'visible'});
    assert.equal((await state()).system_state,'MAINTENANCE');
    for (const route of ['/','/plant','/trends','/controls','/alerts','/maintenance','/settings']) {
      await page.goto(base+route);
      await page.locator('#maintenance-banner').waitFor({state:'visible'});
      assert.equal(await page.locator('#maintenance-banner').innerText(),'MAINTENANCE - OUTPUTS INHIBITED');
    }
    await page.goto(base+'/controls');
    await page.locator('#maintenance-banner').waitFor({state:'visible'});
    await page.locator('[data-command="pump-on"]').click();
    await page.locator('#command-feedback').filter({hasText:'maintenance'}).waitFor();
    assert.equal(await page.locator('#confirm-dialog').evaluate(n=>n.open),false);
    assert.equal(await page.locator('#lighting-upload').isDisabled(),true);
    await page.screenshot({path:path.join(output,'maintenance-controls.png'),fullPage:true});
    await page.goto(base+'/maintenance');
    page.once('dialog',dialog=>dialog.accept());
    await page.locator('[data-workflow="exit_maintenance"]').click();
    await page.locator('#system-state').filter({hasText:'SAFE STOP'}).waitFor();
    page.once('dialog',dialog=>dialog.accept());
    await page.locator('[data-workflow="start"]').click();
    await page.locator('#system-state').filter({hasText:'NORMAL'}).waitFor();
    await page.goto(base+'/firmware');
    assert.equal(await page.locator('#custom').isDisabled(),true);
    assert.equal(await page.locator('#builtin').isDisabled(),true);
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(output,'RESULTS.json'), JSON.stringify({scope:'Browser + synthetic adapters only',viewport:'739x447',
      checks:['cancel has no command','backend confirmation + ACK not physical','maintenance visible on seven screens',
              'inhibited control rejected before dialog/dispatch','firmware controls disabled','exit does not restart; separate confirmed start'],
      pageErrors:errors,status:'PASS'},null,2));
    console.log('PASS: browser workflow, no page errors; screenshot in ' + output);
  } finally {
    if (browser) await browser.close();
    child.kill();
    fs.writeFileSync(path.join(output,'server-output.txt'),logs);
  }
})().catch(error => {console.error(error);process.exitCode=1;});

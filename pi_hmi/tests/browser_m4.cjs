/* Disposable browser + real Flask/SQLite/gateway/event/scheduler integration. */
const {spawn}=require('node:child_process');
const path=require('node:path'),fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.GERM_PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
  const root=path.resolve(__dirname,'../..');
  const output=path.resolve(process.env.GERM_BROWSER_OUTPUT || path.join(root,'build/m4-browser'));
  fs.mkdirSync(output,{recursive:true});
  const child=spawn(process.env.GERM_TEST_PYTHON || 'python',[path.join(__dirname,'browser_m4_host.py')],
    {cwd:root,env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
  let browser,logs='';child.stderr.on('data',chunk=>logs+=chunk);
  try {
    const port=await new Promise((resolve,reject)=>{
      let text='';const timer=setTimeout(()=>reject(Error('Host startup timeout '+logs)),15000);
      child.on('exit',code=>reject(Error('Host exit '+code+' '+logs)));
      child.stdout.on('data',chunk=>{text+=chunk;if(text.includes('\n')){clearTimeout(timer);resolve(JSON.parse(text.split('\n')[0]).port);}});
    });
    browser=await chromium.launch({headless:true,executablePath:process.env.GERM_TEST_BROWSER || undefined});
    const page=await browser.newPage({viewport:{width:739,height:447}}),errors=[];
    page.on('pageerror',error=>errors.push(error.message));const base='http://127.0.0.1:'+port;
    async function workflowDialog(action,accept=true) {
      const opened=page.waitForEvent('dialog');
      const clicked=page.locator(`[data-workflow="${action}"]`).click();
      const dialog=await opened;
      if (accept) await dialog.accept(); else await dialog.dismiss();
      await clicked;
    }
    await page.goto(base+'/settings');
    await page.locator('#grow-profile').waitFor();
    await page.waitForFunction(()=>document.querySelector('#grow-profile').options.length===2);
    await page.locator('#grow-profile').selectOption('basil');
    await page.locator('#grow-name').fill('Browser synthetic basil');
    const created=page.waitForResponse(r=>r.url().endsWith('/api/grow/cycles') && r.request().method()==='POST');
    await page.locator('#create-cycle').click();
    const createdResponse=await created;assert.equal(createdResponse.status(),200,await createdResponse.text());
    await page.locator('#settings-experiment').filter({hasText:'basil · paused'}).waitFor();
    await page.locator('#light-enabled').check();
    await page.locator('#light-start').fill('00:00');await page.locator('#light-end').fill('01:00');
    await page.locator('#schedule-rgb').fill('10,20,30');await page.locator('#mist-enabled').check();
    const saved=page.waitForResponse(r=>r.url().endsWith('/api/grow/schedules') && r.request().method()==='POST');
    await page.locator('#save-schedules').click();
    assert.equal((await saved).status(),200);
    await page.locator('#grow-form-status').filter({hasText:'Configuration committed'}).waitFor();
    await workflowDialog('start',false);
    assert.equal((await (await page.request.get(base+'/api/grow')).json()).cycle.status,'paused');
    const started=page.waitForResponse(r=>r.url().endsWith('/api/workflow') && r.request().method()==='POST');
    await workflowDialog('start');
    const startResult=await (await started).json();
    fs.writeFileSync(path.join(output,'start-debug.json'),JSON.stringify({startResult,state:await (await page.request.get(base+'/api/state')).json()},null,2));
    await page.locator('#grow-summary').filter({hasText:'armed for simulation'}).waitFor();
    await page.goto(base+'/');
    await page.locator('#home-grow-day').filter({hasText:'Grow day 1'}).waitFor();
    assert.equal(await page.locator('#electronics_temperature-value').innerText(),'NO DATA');
    const stale=await page.evaluate(()=>sensorText({value:null,state:'stale',quality_flag:'stale',fault_reason:'stale',age_seconds:5}));
    assert.equal(stale[0],'NO DATA');assert.match(stale[1],/STALE/);
    await page.locator('#home-light-schedule').filter({hasText:'00:00–01:00 UTC'}).waitFor();
    await page.locator('#logging-summary').filter({hasText:'committed'}).waitFor();
    await page.screenshot({path:path.join(output,'home-grow.png'),fullPage:true});
    await page.locator('.content').evaluate(node=>node.scrollTop=node.scrollHeight);
    await page.screenshot({path:path.join(output,'home-details.png'),fullPage:true});
    await page.locator('[data-workflow="pause"]').click();
    await page.locator('#grow-summary').filter({hasText:'paused'}).waitFor();
    await workflowDialog('enter_maintenance');
    await page.locator('#maintenance-banner').waitFor({state:'visible'});
    for (const route of ['/','/plant','/trends','/controls','/alerts','/maintenance','/settings']) {
      await page.goto(base+route);await page.locator('#maintenance-banner').waitFor({state:'visible'});
    }
    await page.screenshot({path:path.join(output,'settings-maintenance.png'),fullPage:true});
    await workflowDialog('exit_maintenance');
    await page.locator('#system-state').filter({hasText:'SAFE STOP'}).waitFor();
    assert.equal((await (await page.request.get(base+'/api/grow')).json()).schedules_armed,false);
    await workflowDialog('complete_cycle');
    await page.locator('#grow-summary').filter({hasText:'complete'}).waitFor();
    await page.locator('#grow-profile').selectOption('spearmint');await page.locator('#create-cycle').click();
    await page.locator('#settings-experiment').filter({hasText:'spearmint · paused'}).waitFor();
    const data=await (await page.request.get(base+'/api/grow')).json();
    assert.equal(data.schedules_armed,false);assert.equal(data.schedules.length,0);
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(output,'RESULTS.json'),JSON.stringify({status:'PASS',scope:'Synthetic loopback host only',viewport:'739x447',pageErrors:errors,
      checks:['basil and spearmint persistent templates','configure host schedules while paused','cancel start has no state change',
        'confirmed cycle start via gateway','home day/schedules/missing electronics','queued vs committed event display','pause/maintenance on seven screens',
        'exit does not restart','complete retains cycle; create spearmint paused']},null,2));
    console.log('PASS: M4 browser HMI + SQLite + gateway + scheduler + event pipeline');
  } finally {if(browser)await browser.close();child.kill();fs.writeFileSync(path.join(output,'server-output.txt'),logs);}
})().catch(error=>{console.error(error);process.exitCode=1;});

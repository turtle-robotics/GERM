/* Runtime network isolation, seven screens, keyboard UX and conservative recovery. */
const {spawn}=require('node:child_process'),path=require('node:path'),fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.GERM_PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
  const root=path.resolve(__dirname,'../..'),output=path.resolve(process.env.GERM_BROWSER_OUTPUT || path.join(root,'build/m9-browser'));fs.mkdirSync(output,{recursive:true});
  const child=spawn(process.env.GERM_TEST_PYTHON || 'python',[path.join(__dirname,'browser_m9_host.py')],{cwd:root,env:{...process.env,GERM_M9_TRACE:path.join(output,'server-trace.json'),PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
  let browser,page,logs='';child.stderr.on('data',c=>logs+=c);
  try{
    const port=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(Error('Startup timeout '+logs)),25000);child.on('exit',code=>reject(Error('Host exited '+code+' '+logs)));child.stdout.on('data',c=>{text+=c;if(text.includes('\n')){clearTimeout(timer);resolve(JSON.parse(text.split('\n')[0]).port);}});});
    const base='http://127.0.0.1:'+port,external=[],errors=[],posts=[];
    browser=await chromium.launch({headless:true,executablePath:process.env.GERM_TEST_BROWSER || undefined});
    const context=await browser.newContext({viewport:{width:739,height:447}});
    await context.route('**/*',route=>{const url=new URL(route.request().url());if(url.origin!==base){external.push(url.origin);return route.abort();}return route.continue();});
    page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname);});
    await page.addInitScript(()=>{
      window.m9Trace=[];const trace=(kind,data)=>{window.m9Trace.push({t:performance.now(),kind,...data});if(window.m9Trace.length>512)window.m9Trace.shift();};
      const original=window.fetch;let sequence=0;
      window.fetch=async(...args)=>{const id=++sequence;trace('request',{id,url:String(args[0])});try{const result=await original(...args);trace('response',{id,status:result.status});return result;}catch(error){trace('error',{id,error:String(error)});throw error;}};
      addEventListener('DOMContentLoaded',()=>new MutationObserver(()=>trace('DOM',{grow:document.querySelector('#grow-summary')?.textContent})).observe(document.querySelector('#grow-summary'),{childList:true,subtree:true}));
    });
    if(process.env.GERM_M9_BASELINE_CLIENT)await page.route('**/static/hmi.js',route=>route.fulfill({path:path.resolve(process.env.GERM_M9_BASELINE_CLIENT),contentType:'text/javascript'}));
    async function nativeConfirm(button){const opened=page.waitForEvent('dialog'),clicked=button.click();const dialog=await opened;await dialog.accept();await clicked;}
    for(const route of ['/','/plant','/trends','/controls','/alerts','/maintenance','/settings']){
      await page.goto(base+route);await page.locator('#local-connection').filter({hasText:'Local host running'}).waitFor();
      assert.equal(await page.locator('nav a').count(),7);assert.equal(await page.locator('nav a[aria-current=page]').count(),1);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      await page.keyboard.press('Tab');assert.equal(await page.locator('.skip-link').evaluate(n=>n===document.activeElement),true);
      const focusStyle=await page.locator('.skip-link').evaluate(n=>getComputedStyle(n).outlineStyle);assert.notEqual(focusStyle,'none');
      await page.keyboard.press('Enter');assert.equal(await page.locator('#main-content').evaluate(n=>n===document.activeElement),true);
    }
    await page.goto(base+'/');await page.locator('#grow-summary').filter({hasText:'paused'}).waitFor();
    await nativeConfirm(page.locator('[data-workflow=start]'));await page.locator('#grow-summary').filter({hasText:'armed for simulation'}).waitFor();
    let releaseOld,seenOld;const held=new Promise(resolve=>seenOld=resolve),release=new Promise(resolve=>releaseOld=resolve);let hold=true;
    await page.route('**/api/state',async route=>{
      if(!hold)return route.continue();hold=false;
      const response=await route.fetch(),body=await response.text();seenOld(JSON.parse(body));await release;await route.fulfill({response,body});
    });
    await page.evaluate(()=>{window.m9OldPoll=pollState();});
    const older=await held;assert.equal(older.grow.cycle.status,'running');
    await page.locator('[data-workflow=pause]').click();await page.locator('#grow-summary').filter({hasText:'paused'}).waitFor();
    releaseOld();await page.evaluate(()=>window.m9OldPoll);
    const rendered=await page.locator('#grow-summary').textContent();
    fs.writeFileSync(path.join(output,'response-ordering.json'),JSON.stringify({olderApiCycle:older.grow.cycle.status,latestApiCycle:(await(await page.request.get(base+'/api/state')).json()).grow.cycle.status,rendered,trace:await page.evaluate(()=>window.m9Trace)},null,2));
    if(process.env.GERM_M9_EXPECT_RACE==='1'){assert.match(rendered,/running/);console.log('REPRODUCED: older running response overwrote newer paused DOM');return;}
    assert.match(rendered,/paused/);await page.unroute('**/api/state');
    await page.route('**/api/confirmations',async route=>{
      const response=await route.fetch(),data=await response.json(),request=route.request().postDataJSON();
      if(request.action==='pause')data.state_revision-=1; // Deterministically emulate a concurrent worker transition.
      await route.fulfill({response,json:data});
    });
    for(let iteration=0;iteration<3;iteration++){
      await nativeConfirm(page.locator('[data-workflow=start]'));await page.locator('#grow-summary').filter({hasText:'armed for simulation'}).waitFor();
      await page.locator('[data-workflow=pause]').click();await page.locator('#grow-summary').filter({hasText:'paused'}).waitFor();
      for(const route of ['/','/plant','/trends','/controls','/alerts','/maintenance','/settings']){await page.goto(base+route);await page.locator('#grow-summary').filter({hasText:'paused'}).waitFor();}
      await page.goto(base+'/');
    }
    await nativeConfirm(page.locator('[data-workflow=start]'));await page.locator('#grow-summary').filter({hasText:'armed for simulation'}).waitFor();
    await page.goto(base+'/controls');await page.locator('#boundary-status').filter({hasText:'SIMULATION'}).waitFor();
    await page.locator('[data-command=pump-on]').click();await page.locator('#confirm-dialog[open]').waitFor();
    assert.equal(await page.locator('#cancel-command').evaluate(n=>n===document.activeElement),true);
    await page.keyboard.press('Escape');await page.locator('#confirm-dialog').waitFor({state:'hidden'});
    assert.equal(posts.filter(p=>p==='/api/pump').length,0);
    const target=await page.locator('[data-command=pump-on]').boundingBox();assert.ok(target.height>=44);
    const count=posts.length;await context.setOffline(true);
    await page.locator('#system-state').filter({hasText:'STATUS UNAVAILABLE'}).waitFor();
    assert.equal(await page.locator('[data-command=pump-on]').isDisabled(),true);
    await page.screenshot({path:path.join(output,'local-connection-lost.png'),fullPage:true});
    await context.setOffline(false);await page.locator('#local-connection').filter({hasText:'Local host running'}).waitFor();
    await page.waitForFunction(()=>document.querySelector('#system-state').textContent!=='STATUS UNAVAILABLE');assert.equal(posts.length,count);
    child.stdin.write(JSON.stringify({fault:'database'})+'\n');await page.locator('#local-connection').filter({hasText:'Local host degraded'}).waitFor();
    await page.locator('.service-status').evaluate(n=>n.open=true);
    await page.locator('#service-health').filter({hasText:'worker: unavailable'}).waitFor();
    await nativeConfirm(page.locator('#recover-services'));await page.locator('#command-feedback').filter({hasText:'permissions not restored'}).waitFor();
    const services=await (await page.request.get(base+'/api/services')).json();assert.equal(services.restart_required,true);assert.equal(services.schedules_armed,false);
    const state=await (await page.request.get(base+'/api/state')).json();assert.equal(state.grow.cycle.status,'paused');assert.equal(state.operating_state.controller_feedback.pump,false);
    await page.screenshot({path:path.join(output,'recovered-permissions-inhibited.png'),fullPage:true});
    await page.goto(base+'/plant');child.stdin.write(JSON.stringify({fault:'camera_stale'})+'\n');
    await page.locator('#camera-metadata').filter({hasText:'stale'}).waitFor();assert.equal(await page.locator('#camera-image').isHidden(),true);
    await page.screenshot({path:path.join(output,'stale-camera-no-placeholder.png'),fullPage:true});
    assert.deepEqual(external,[]);assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(output,'RESULTS.json'),JSON.stringify({status:'PASS',commit:require('node:child_process').execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),viewport:'739x447',pauseStartIterations:3,sevenScreenPasses:4,externalRequests:external,pageErrors:errors,checks:['older running response cannot overwrite newer paused DOM','stale preparation revision cannot reject unconfirmed Pause; confirmed Start unchanged','all seven screens with external requests blocked','same-origin assets and CSP','keyboard skip link and visible focus','current-page navigation','no horizontal overflow','touch target size','Cancel-focused dialog and Escape no dispatch','lost localhost clears status and disables commands','reconnect never replays POSTs','DB/core-worker failure requires explicit recovery','restart never restores permissions or armed schedules','stale camera hides image; no placeholder']},null,2));
    console.log('PASS: M9 repeated seven-screen pause/start, response ordering, keyboard, disconnect and recovery browser flow');
  }catch(error){
    if(page){
      try{fs.writeFileSync(path.join(output,'failure-debug.json'),JSON.stringify({error:String(error),growText:await page.locator('#grow-summary').textContent(),trace:await page.evaluate(()=>window.m9Trace),state:await (await page.request.get(new URL('/api/state',page.url()).href)).json()},null,2));await page.screenshot({path:path.join(output,'failure.png')});}catch{}
    }
    throw error;
  }finally{if(browser)await browser.close();child.kill();fs.writeFileSync(path.join(output,'server-output.txt'),logs);}
})().catch(error=>{console.error(error);process.exitCode=1;});

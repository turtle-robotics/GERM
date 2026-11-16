/* Actual Chromium/Flask/SQLite/JPEG backup -> preflight -> isolated restore. */
const {spawn}=require('node:child_process'),path=require('node:path'),fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {chromium}=require(process.env.GERM_PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
  const root=path.resolve(__dirname,'../..'),output=path.resolve(process.env.GERM_BROWSER_OUTPUT || path.join(root,'build/m7-browser'));fs.mkdirSync(output,{recursive:true});
  const child=spawn(process.env.GERM_TEST_PYTHON || 'python',[path.join(__dirname,'browser_m7_host.py')],{cwd:root,env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
  let browser,logs='';child.stderr.on('data',c=>logs+=c);
  try{
    const port=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(Error('Host startup timeout '+logs)),20000);child.on('exit',code=>reject(Error('Host exit '+code+' '+logs)));child.stdout.on('data',c=>{text+=c;if(text.includes('\n')){clearTimeout(timer);resolve(JSON.parse(text.split('\n')[0]).port);}});});
    browser=await chromium.launch({headless:true,executablePath:process.env.GERM_TEST_BROWSER || undefined});
    const page=await browser.newPage({viewport:{width:739,height:447}}),errors=[],base='http://127.0.0.1:'+port;page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base+'/settings');await page.locator('#storage-capacity').filter({hasText:'Observed host volume'}).waitFor();
    assert.equal(await page.locator('nav a').count(),7);await page.locator('#storage-estimate').filter({hasText:'Estimated working'}).waitFor();
    const created=page.waitForResponse(r=>r.url().endsWith('/api/storage/jobs') && r.request().method()==='POST');
    await page.locator('#storage-backup').click();const backup=(await (await created).json()).request_id;
    await page.locator('#storage-job-status').filter({hasText:'backup · complete'}).waitFor();
    const url=await page.locator('#storage-download').getAttribute('href'),response=await page.request.get(base+url),bytes=await response.body();
    assert.equal(response.status(),200);assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),response.headers()['x-germ-sha256']);
    fs.writeFileSync(path.join(output,'verified-backup.zip'),bytes);
    await page.locator('#storage-source').selectOption(backup);assert.equal(await page.locator('#storage-restore').isDisabled(),true);
    await page.locator('#storage-verify').click();await page.locator('#storage-job-status').filter({hasText:'verify · complete'}).waitFor();
    await page.locator('#storage-preflight').click();await page.locator('#storage-job-status').filter({hasText:'preflight · complete'}).waitFor();
    const dialogOpened=page.waitForEvent('dialog'),clicked=page.locator('#storage-restore').click();const dialog=await dialogOpened;await dialog.accept();await clicked;
    await page.locator('#storage-job-status').filter({hasText:'offline copy verified; running system unchanged'}).waitFor();
    await page.locator('#storage-report').evaluate(node=>node.closest('details').open=true);
    const report=JSON.parse(await page.locator('#storage-report').textContent());assert.equal(report.restore_activation_allowed,false);assert.equal(report.runtime_attached,false);assert.equal(report.images_restored,1);
    await page.locator('#storage-job-status').evaluate(node=>node.scrollIntoView({block:'center'}));await page.screenshot({path:path.join(output,'offline-restore.png'),fullPage:true});
    await page.reload();await page.locator('#storage-job-status').filter({hasText:'offline copy verified'}).waitFor();
    child.stdin.write(JSON.stringify({fault:'missing_image'})+'\n');await page.locator('#storage-backup').click();
    await page.locator('#storage-job-status').filter({hasText:'backup · incomplete'}).waitFor();assert.equal(await page.locator('#storage-download').isHidden(),true);
    await page.locator('#storage-job-status').evaluate(node=>node.scrollIntoView({block:'center'}));await page.screenshot({path:path.join(output,'incomplete-backup.png'),fullPage:true});
    child.stdin.write(JSON.stringify({fault:'disk_full'})+'\n');await page.locator('#storage-backup').click();
    await page.locator('#storage-job-status').filter({hasText:'backup · failed'}).waitFor();await page.locator('#storage-job-status').filter({hasText:'insufficient free space'}).waitFor();
    assert.equal(await page.locator('#storage-download').isHidden(),true);await page.screenshot({path:path.join(output,'disk-full.png'),fullPage:true});
    await page.route('**/api/storage',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Injected storage unavailable'})}));
    await page.locator('#storage-refresh').click();await page.locator('#storage-capacity').filter({hasText:'Storage unavailable'}).waitFor();
    assert.equal(await page.locator('#storage-backup').isDisabled(),true);assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(output,'RESULTS.json'),JSON.stringify({status:'PASS',viewport:'739x447',pageErrors:errors,checks:['seven navigation screens preserved','observed capacity versus estimated backup demand','consistent verified backup and SHA download','verify and restore preflight','explicit isolated restore confirmation','offline report no activation','last job after reload','missing image incomplete no download','disk-full failure no deletion','unavailable measurements disable actions']},null,2));
    console.log('PASS: M7 inventory, backup, verification, offline restore and storage fault HMI');
  }finally{if(browser)await browser.close();child.kill();fs.writeFileSync(path.join(output,'server-output.txt'),logs);}
})().catch(error=>{console.error(error);process.exitCode=1;});

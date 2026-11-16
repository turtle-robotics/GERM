/* Full synthetic Flask/SQLite/camera/local inference/outbox browser flow. */
const {spawn}=require('node:child_process'),path=require('node:path'),fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.GERM_PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
  const root=path.resolve(__dirname,'../..'),output=path.resolve(process.env.GERM_BROWSER_OUTPUT || path.join(root,'build/m5-browser'));
  fs.mkdirSync(output,{recursive:true});
  const child=spawn(process.env.GERM_TEST_PYTHON || 'python',[path.join(__dirname,'browser_m5_host.py')],
    {cwd:root,env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
  let browser,logs='';child.stderr.on('data',c=>logs+=c);
  try {
    const port=await new Promise((resolve,reject)=>{
      let text='';const timer=setTimeout(()=>reject(Error('Host startup timeout '+logs)),20000);
      child.on('exit',code=>reject(Error('Host exit '+code+' '+logs)));
      child.stdout.on('data',c=>{text+=c;if(text.includes('\n')){clearTimeout(timer);resolve(JSON.parse(text.split('\n')[0]).port);}});
    });
    browser=await chromium.launch({headless:true,executablePath:process.env.GERM_TEST_BROWSER || undefined});
    const page=await browser.newPage({viewport:{width:739,height:447}}),errors=[],base='http://127.0.0.1:'+port;
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(base+'/plant');
    await page.locator('.camera-badge').filter({hasText:'SYNTHETIC CAMERA'}).waitFor();
    await page.waitForFunction(()=>document.querySelector('#capture-plant').options.length===2);
    await page.locator('#capture-plant').selectOption({index:1});
    async function saveAndAnalyze() {
      const saved=page.waitForResponse(r=>r.url().endsWith('/api/camera/capture') && r.request().method()==='POST');
      await page.locator('#capture-button').click();const response=await saved;
      assert.equal(response.status(),201);const capture=await response.json();
      assert.equal(capture.image.width_px,320);assert.equal(capture.image.height_px,180);
      assert.equal(capture.metadata_committed,true);assert.ok(capture.image.plant_id);
      const analyzed=page.waitForResponse(r=>r.url().endsWith('/api/ml/analyze') && r.request().method()==='POST');
      await page.locator('#analyze-button').click();const inferred=await analyzed;
      assert.equal(inferred.status(),200);const result=(await inferred.json()).result;
      assert.equal(result.image_id,capture.image.image_id);return result;
    }
    const low=await saveAndAnalyze();assert.equal(low.predicted_class,'uncertain');assert.equal(low.alert_eligible,0);
    await page.locator('#ml-class').filter({hasText:'Uncertain / review required'}).waitFor();
    await page.locator('#model-status').filter({hasText:'SYNTHETIC CONTRACT ONLY'}).waitFor();
    await page.locator('.content').evaluate(n=>n.scrollTop=0);
    await page.screenshot({path:path.join(output,'synthetic-capture.png'),fullPage:true});
    await page.locator('#ml-class').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(output,'uncertain-model.png'),fullPage:true});
    const first=await saveAndAnalyze();assert.equal(first.abnormal_streak,1);assert.equal(first.alert_eligible,0);
    const second=await saveAndAnalyze();assert.equal(second.abnormal_streak,2);assert.equal(second.alert_eligible,1);
    await page.locator('#ml-detail').filter({hasText:'not a plant diagnosis'}).waitFor();
    await page.locator('#saved-image-age').filter({hasText:'committed'}).waitFor();
    await page.locator('#capture-schedule-enabled').check();
    const configured=page.waitForResponse(r=>r.url().endsWith('/api/camera/schedule') && r.request().method()==='POST');
    await page.locator('#save-capture-schedule').click();assert.equal((await configured).status(),200);
    await page.locator('#media-schedule-status').filter({hasText:'Schedule committed'}).waitFor();
    const recovered=page.waitForResponse(r=>r.url().endsWith('/api/media/recover') && r.request().method()==='POST');
    await page.locator('#recover-captures').click();assert.equal((await recovered).status(),200);
    child.stdin.write(JSON.stringify({camera:'stale'})+'\n');
    await page.locator('#camera-metadata').filter({hasText:'stale'}).waitFor();
    assert.equal(await page.locator('#camera-image').isHidden(),true);
    assert.equal(await page.locator('#capture-button').isDisabled(),true);
    await page.locator('.content').evaluate(n=>n.scrollTop=0);
    await page.screenshot({path:path.join(output,'stale-camera.png'),fullPage:true});
    child.stdin.write(JSON.stringify({camera:'ready',model:'unavailable'})+'\n');
    await page.locator('#model-status').filter({hasText:'No model configured'}).waitFor();
    assert.equal(await page.locator('#analyze-button').isDisabled(),true);
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(output,'RESULTS.json'),JSON.stringify({status:'PASS',scope:'Synthetic frames/contract model only; no real plant model',viewport:'739x447',pageErrors:errors,
      checks:['synthetic camera label and plant linkage','exact JPEG metadata and indexed file view','low confidence uncertain',
        'two reviewed fixture abnormal classifications only','queued/committed outbox display','hourly schedule configuration and recovery',
        'stale camera hides preview and denies capture','unavailable model disables analysis','no placeholder/plant diagnosis']},null,2));
    console.log('PASS: M5 synthetic capture, inference, recovery and browser fault states');
  } finally {if(browser)await browser.close();child.kill();fs.writeFileSync(path.join(output,'server-output.txt'),logs);}
})().catch(error=>{console.error(error);process.exitCode=1;});

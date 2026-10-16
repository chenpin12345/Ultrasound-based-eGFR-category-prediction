// Only a disposable loopback server; no production data, login, camera or medical actions.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const evidence=process.env.ISU_UI_EVIDENCE;
if(!evidence||!path.isAbsolute(evidence)||fs.existsSync(evidence))throw Error('Use a new absolute evidence directory');
fs.mkdirSync(evidence,{recursive:true});
const port='18765',base='http://127.0.0.1:'+port;
const env={...process.env,ISU_AI_DATA_DIR:path.join(evidence,'three-zone-ui-data'),ISU_AI_MODELS_DIR:path.join(evidence,'models'),
 ISU_AI_CLINICAL_DIR:path.join(evidence,'clinical'),ISU_AI_REPORTS_DIR:path.join(evidence,'reports'),ISU_AI_RUNTIME_DIR:path.join(evidence,'runtime'),
 ISU_AI_REFERENCE_FEATURES_DIR:path.join(evidence,'features'),ISU_AI_FRONTEND_DIST:path.join(root,'frontend/dist'),
 ISU_AI_REQUIRE_EXISTING_DATABASES:'false',ISU_UI_TEST_PORT:port};
env.ISU_AI_DATABASE_URL='sqlite:///'+path.join(env.ISU_AI_DATA_DIR,'isu_ai.sqlite3').replaceAll('\\','/');
const server=spawn(path.join(root,'.venv/Scripts/python.exe'),[path.join(__dirname,'three_zones_smoke_server.py')],{cwd:root,env,windowsHide:true,stdio:['ignore','pipe','pipe']});
let log='';server.stdout.on('data',chunk=>log+=chunk);server.stderr.on('data',chunk=>log+=chunk);
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 let browser;
 try{
  for(let attempt=0;attempt<100;attempt++){if(server.exitCode!==null)throw Error(log);try{if((await fetch(base+'/api/health')).ok)break;}catch{}if(attempt===99)throw Error('Isolated server timeout');await delay(100);}
  browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
  const errors=[],serverErrors=[];page.on('pageerror',e=>errors.push(e.message));
  context.on('response',response=>{if(response.status()>=500)serverErrors.push({url:response.url(),status:response.status()})});
  const timings=[];
  async function open(url,heading){const start=Date.now();await page.goto(base+url);await page.getByRole('heading',{name:heading,exact:true}).waitFor();timings.push({url,ms:Date.now()-start});}
  await open('/','研究儀表板');assert.equal(new URL(page.url()).pathname,'/research');
  assert.equal(await page.getByRole('heading',{name:'登入'}).count(),0);
  await page.getByRole('link',{name:'模型區',exact:true}).click();await page.getByRole('heading',{name:'模型總覽',exact:true}).waitFor();
  await page.getByRole('link',{name:'模型管理',exact:true}).click();await page.getByText('共 237 個模型',{exact:false}).waitFor();
  await page.getByRole('button',{name:'下一頁',exact:true}).click();await page.getByText('第 2 頁',{exact:false}).waitFor();
  await page.getByLabel('搜尋模型名稱').fill('0236');await page.getByText('共 1 個模型',{exact:false}).waitFor();
  await page.getByText('第 1 頁',{exact:false}).waitFor();
  await page.getByRole('link',{name:'查看設定與追溯',exact:true}).click();await page.getByRole('heading',{name:'隔離介面測試模型 0236'}).waitFor();
  await page.getByText('設定未核實',{exact:true}).waitFor();
  await page.screenshot({path:path.join(evidence,'model-detail-desktop.png'),fullPage:true});
  await open('/models/fixture-0236?dataset_id=retained#result','隔離介面測試模型 0236');
  assert.equal(new URL(page.url()).pathname,'/model-center/models/fixture-0236');assert.equal(new URL(page.url()).search,'?dataset_id=retained');assert.equal(new URL(page.url()).hash,'#result');
  await open('/model-center/evaluations','模型評估');
  await page.getByText('建立評估：選擇模型 → 資料 → 確認範圍 → 提交',{exact:true}).click();
  await page.screenshot({path:path.join(evidence,'evaluation-desktop.png'),fullPage:true});
  await page.getByRole('link',{name:'醫師工作區',exact:true}).click();await page.getByRole('heading',{name:'超音波設備接收',exact:true}).waitFor();
  await open('/clinical/monitor','紀錄與作業監控');
  await page.getByText('共 537 筆',{exact:false}).waitFor();
  await page.getByRole('button',{name:'下一頁紀錄',exact:true}).click();await page.getByText('第 2 頁',{exact:false}).waitFor();
  await page.getByLabel('搜尋名稱或識別碼').fill('UI0536');await page.getByText('共 1 筆',{exact:false}).waitFor();
  await page.getByText('隔離介面測試病人 0536 · UI0536',{exact:true}).waitFor();
  await page.screenshot({path:path.join(evidence,'clinical-monitor-desktop.png'),fullPage:true});
  await page.getByRole('link',{name:'工作區',exact:true}).click();await page.getByRole('heading',{name:'研究儀表板',exact:true}).waitFor();
  await open('/research/inference?model_id=fixture-0236','AI 推論');await page.getByRole('option',{name:/隔離介面測試模型 0236/}).waitFor({state:'attached'});
  assert.equal(await page.getByLabel('分類模型',{exact:true}).inputValue(),'fixture-0236');
  await open('/research/ai-judgment','AI判斷');
  await page.getByRole('button',{name:/僅圖片 OnlyIMG/}).click();
  await open('/model-center/models','模型管理');await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(evidence,'models-390.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1),false,'Model page horizontal overflow');
  await open('/model-center/evaluations','模型評估');await page.getByText('建立評估：選擇模型 → 資料 → 確認範圍 → 提交',{exact:true}).click();
  await page.screenshot({path:path.join(evidence,'evaluation-390.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1),false,'Evaluation page horizontal overflow');
  await page.keyboard.press('Tab');assert.ok(await page.evaluate(()=>document.activeElement!==document.body));
  await open('/clinical/monitor','紀錄與作業監控');await page.getByText('共 537 筆',{exact:false}).waitFor();
  await page.screenshot({path:path.join(evidence,'clinical-monitor-390.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1),false,'Clinical monitor horizontal overflow');
  const second=await context.newPage();await second.goto(base+'/research');await second.getByRole('heading',{name:'研究儀表板',exact:true}).waitFor();
  await page.reload();await page.getByRole('heading',{name:'紀錄與作業監控',exact:true}).waitFor();
  const auth=await context.request.get(base+'/api/local-session');assert.equal(auth.status(),200);
  assert.equal((await context.request.post(base+'/api/auth/login',{data:{}})).status(),410);
  // Mutations below affect only the fresh synthetic fixture database.
  await page.setViewportSize({width:1440,height:1000});
  await page.getByLabel('搜尋名稱或識別碼').fill('UI0536');await page.getByText('共 1 筆',{exact:false}).waitFor();
  await second.goto(base+'/clinical/monitor');await second.getByRole('heading',{name:'紀錄與作業監控'}).waitFor();
  await second.getByLabel('搜尋名稱或識別碼').fill('UI0536');await second.getByText('共 1 筆',{exact:false}).waitFor();
  await page.getByRole('button',{name:'移至回收區',exact:true}).click();
  const lifecycle=page.getByRole('dialog');await lifecycle.getByLabel('操作理由（必填）').fill('隔離測試：跨分頁回收及恢復');
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(evidence,'lifecycle-dialog-390.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1),false);
  await lifecycle.getByRole('button',{name:'確認移至回收區',exact:true}).click();
  await second.getByText('共 0 筆',{exact:false}).waitFor();
  await page.getByLabel('生命週期／回收區').selectOption('trashed');await page.getByText('共 1 筆',{exact:false}).waitFor();
  await page.getByRole('button',{name:'恢復',exact:true}).click();await lifecycle.getByLabel('操作理由（必填）').fill('隔離測試恢復');
  await lifecycle.getByRole('button',{name:'確認恢復',exact:true}).click();await second.getByText('共 1 筆',{exact:false}).waitFor();
  const exam=await page.evaluate(async()=>{
    const session=await (await fetch('/api/local-session')).json();
    const response=await fetch('/api/clinical/exams',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf},body:JSON.stringify({kind:'demo',title:'隔離報告離頁測試'})});
    if(!response.ok)throw Error('Fixture exam creation failed '+response.status);
    return response.json();
  });
  await open('/clinical/reports?exam='+exam.id,'報告中心');
  await page.getByLabel('檢查所見',{exact:true}).fill('尚未保存的隔離測試文字');
  await page.getByRole('link',{name:'模型區',exact:true}).click();
  await page.getByRole('dialog',{name:'報告尚未保存'}).waitFor();
  await page.screenshot({path:path.join(evidence,'unsaved-report-390.png'),fullPage:true});
  assert.equal(await page.getByRole('button',{name:'留在此頁'}).evaluate(element=>document.activeElement===element),true,'Safe initial dialog focus');
  await page.keyboard.press('Escape');assert.equal(await page.getByLabel('檢查所見',{exact:true}).inputValue(),'尚未保存的隔離測試文字');
  await page.getByRole('link',{name:'模型區',exact:true}).click();await page.getByRole('button',{name:'保存草稿並離開'}).click();
  await page.getByRole('heading',{name:'模型總覽',exact:true}).waitFor();
  const saved=await page.evaluate(async()=>{const response=await fetch('/api/clinical/monitor/reports?limit=50');if(!response.ok)throw Error('Report query');return response.json()});
  assert.equal(saved.total,1);
  const reportUrl='/clinical/reports?report='+saved.items[0].id;
  await open(reportUrl,'報告中心');await page.getByLabel('檢查所見',{exact:true}).fill('本分頁尚未保存');
  await second.goto(base+reportUrl);await second.getByLabel('檢查所見',{exact:true}).fill('另一分頁的新版本');
  await second.getByRole('button',{name:'保存草稿版本',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'另一個操作已建立新報告版本'}).waitFor();
  assert.equal(await page.getByLabel('檢查所見',{exact:true}).inputValue(),'本分頁尚未保存');
  assert.equal(await page.getByRole('button',{name:'保存草稿版本',exact:true}).isDisabled(),true);
  await page.screenshot({path:path.join(evidence,'report-conflict-390.png'),fullPage:true});
  // The dirty first tab intentionally stays bound to v1. A separate reader
  // watches v2, so the test never requires replacing the dirty tab's snapshot.
  const pdfWatch=await context.newPage();pdfWatch.on('pageerror',e=>errors.push(e.message));
  await pdfWatch.goto(base+reportUrl);await pdfWatch.getByRole('heading',{name:'報告中心',exact:true}).waitFor();
  await second.getByRole('button',{name:'產生 PDF',exact:true}).click();
  await second.getByRole('link',{name:'下載此版本 PDF',exact:true}).waitFor();
  const originalPdf=await second.getByRole('link',{name:'下載此版本 PDF',exact:true}).getAttribute('href');
  await pdfWatch.getByRole('link',{name:'下載此版本 PDF',exact:true}).waitFor();
  // Iframe streaming completes before deletion; the server returns 409 if busy.
  await second.locator('iframe[title="報告 PDF 預覽"]').waitFor();
  await second.getByRole('button',{name:'刪除此 PDF 檔案',exact:true}).click();
  await second.getByLabel('PDF 刪除理由（必填）',{exact:true}).fill('隔離瀏覽器刪除與重建驗證');
  await second.getByRole('button',{name:'確認刪除 PDF',exact:true}).click();
  await second.getByText('指定 PDF 檔已刪除。報告與分析版本保留；預覽或下載不會重新產生。',{exact:true}).waitFor();
  await pdfWatch.locator('iframe[title="報告 PDF 預覽"]').waitFor({state:'detached'});
  assert.equal((await context.request.get(base+originalPdf)).status(),410);
  await second.getByRole('button',{name:'重新產生 PDF',exact:true}).click();
  await second.getByRole('link',{name:'下載此版本 PDF',exact:true}).waitFor();
  const rebuiltPdf=await second.getByRole('link',{name:'下載此版本 PDF',exact:true}).getAttribute('href');
  assert.notEqual(rebuiltPdf,originalPdf);
  assert.equal((await context.request.get(base+originalPdf)).status(),410);
  await second.setViewportSize({width:390,height:844});
  await second.screenshot({path:path.join(evidence,'pdf-controls-390.png'),fullPage:true});
  assert.equal(await second.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1),false);
  await second.goto(base+'/clinical/monitor?section=cleanup');
  await second.getByRole('button',{name:'重試暫存清理',exact:true}).click();
  const cleanupDialog=second.getByRole('dialog',{name:'確認重試暫存清理'});
  await cleanupDialog.waitFor();
  assert.equal(await cleanupDialog.getByRole('button',{name:'確認重試清理',exact:true}).isDisabled(),true);
  await cleanupDialog.getByLabel('重試理由（必填）').fill('隔離瀏覽器中斷恢復驗證');
  await second.screenshot({path:path.join(evidence,'cleanup-dialog-390.png'),fullPage:true});
  assert.equal(await second.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1),false);
  await cleanupDialog.getByRole('button',{name:'確認重試清理',exact:true}).click();
  await second.getByText('指定作業的未保存暫存影像已刪除，不能從回收區恢復；作業紀錄仍保留。',{exact:true}).waitFor();
  assert.equal(await second.getByRole('button',{name:'重試暫存清理',exact:true}).count(),0);
  await second.goto(base+'/clinical/monitor?section=previews');
  await second.getByText('共 1 筆',{exact:false}).waitFor();
  await second.getByLabel('作業／報告狀態').selectOption('cancelled');
  await second.getByLabel('資料類型').selectOption('demo');
  await second.getByText('採用方案：隔離預覽方案',{exact:true}).waitFor();
  await second.getByText(/隔離預覽已停止；未保存影像不自動重試/).waitFor();
  assert.equal(await second.getByRole('button',{name:'使用同一方案重試分析',exact:true}).count(),0);
  await second.screenshot({path:path.join(evidence,'preview-history-390.png'),fullPage:true});
  assert.equal(await second.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1),false);
  assert.deepEqual(errors,[]);
  assert.deepEqual(serverErrors,[],'Unexpected server errors during browser acceptance');
  fs.writeFileSync(path.join(evidence,'summary.json'),JSON.stringify({passed:true,scope:'isolated browser software test; no hardware or model-accuracy claim',checks:['local bootstrap','three-zone links','237 models pagination','537 patients pagination','search resets page','deep link query/hash','missing configuration visible','AI inference and judgment retained','390px overflow','keyboard focus','same-context two tabs','legacy login disabled','lifecycle trash/restore cross-tab invalidation','unsaved report Escape and save before navigation','dirty report cross-tab version conflict','explicit PDF generation/delete/rebuild','PDF cross-tab iframe invalidation and old URL tombstone'],timings,pageErrors:errors},null,2));
  console.log(JSON.stringify({passed:true,timings}));
 }catch(error){
   if(browser)for(const [index,failedPage] of browser.contexts()[0].pages().entries()){
     fs.writeFileSync(path.join(evidence,`failure-${index}.txt`),JSON.stringify({url:failedPage.url(),text:await failedPage.locator('body').innerText()},null,2));
     await failedPage.screenshot({path:path.join(evidence,`failure-${index}.png`),fullPage:true});
   }
   throw error;
 }finally{if(browser)await browser.close();server.kill();fs.writeFileSync(path.join(evidence,'server.log'),log);}
})().catch(e=>{console.error(e);process.exitCode=1});

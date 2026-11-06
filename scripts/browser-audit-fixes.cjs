/* Deterministic UI regressions. Every API request is mocked; no live accounts or data are changed. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:8000';
const user = {id:'audit-teacher',username:'audit_teacher',full_name:'Audit Teacher',role:'teacher'};
const course = id => ({id,title:id==='target'?'Target class':`Class ${id}`,description:'',owner_id:user.id,is_public:true,archived:false,can_manage:true,can_delete:true});
const step = (key,id) => ({key,title:key,module:'Module',kind:'reading',required:true,prerequisites:[],lesson_version_id:id,problem_version_id:null});
const pathModel = (id,steps) => ({id,path_id:`p${id}`,title:`Path ${id.toUpperCase()}`,description:'',languages:['c17'],sequential:true,status:'draft',revision:1,edit_revision:1,steps});

(async()=>{
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const errors = [];
  let releaseOld, oldEntered, saved;
  const oldHeld = new Promise(resolve => oldEntered=resolve);
  const oldGate = new Promise(resolve => releaseOld=resolve);
  const models = {a:pathModel('a',[step('a1','la'),step('a2','la')]),b:pathModel('b',[step('b1','lb')])};
  async function prepare(page) {
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const req=route.request(),url=new URL(req.url()),p=url.pathname;
      if(p==='/' || p.startsWith('/assets/')) return route.continue();
      if(req.method()==='PUT' && p==='/author/path-versions/b') {
        saved=req.postDataJSON();
        return route.fulfill({json:{...models.b,...saved,edit_revision:2}});
      }
      if(req.method()!=='GET') throw Error('Unexpected mocked write: '+p);
      if(p==='/auth/me') return route.fulfill({json:user});
      if(p==='/my/learning' || p==='/submissions') return route.fulfill({json:[]});
      if(p==='/my/stats') return route.fulfill({json:{accepted_exercises:7}});
      if(p==='/courses') {
        const offset=Number(url.searchParams.get('offset')||0);
        return route.fulfill({json:offset===100?[course('target')]:Array.from({length:100},(_,i)=>course(`other-${i}`))});
      }
      if(/^\/courses\/[^/]+$/.test(p)) return route.fulfill({json:course(p.split('/')[2])});
      if(/^\/author\/path-versions\/[ab]$/.test(p)) return route.fulfill({json:models[p.at(-1)]});
      if(p==='/author/courses/ca/content') {
        oldEntered(); await oldGate;
        return route.fulfill({json:{lessons:[{id:'la',title:'A material',status:'published',archived:false}],problems:[]}});
      }
      if(p==='/author/courses/cb/content') return route.fulfill({json:{lessons:Number(url.searchParams.get('offset')||0)===100
        ?[{id:'lb',title:'B material',revision:1,status:'published',archived:false}]
        :Array.from({length:100},(_,i)=>({id:`lb-${i}`,title:`Material ${i}`,revision:1,status:'published',archived:false})),problems:[]}});
      if(p==='/author/courses/target/content') return route.fulfill({json:{lessons:[],problems:[]}});
      if(p==='/author/courses/target/paths') return route.fulfill({json:[]});
      throw Error('Unexpected mocked read: '+p);
    });
    await page.goto(base);
    await page.getByRole('heading',{name:'Halo, Audit Teacher.',exact:true}).waitFor();
  }
  try {
    const racePage = await browser.newPage();
    await prepare(racePage);
    await racePage.evaluate(async()=>{
      const core=await import('/assets/core.js'),studio=await import('/assets/studio.js');
      core.state.route=1000;
      window.oldEditor=studio.renderStudio(['path-editor','a','ca'],1000);
    });
    await oldHeld;
    await racePage.evaluate(async()=>{
      const core=await import('/assets/core.js'),studio=await import('/assets/studio.js');
      core.state.route=1001;
      document.querySelector('#app').innerHTML=await studio.renderStudio(['path-editor','b','cb'],1001);
    });
    assert.match(await racePage.locator('#step-target-0 option:checked').textContent(),/B material/);
    releaseOld();
    await racePage.evaluate(async()=>{
      await window.oldEditor;
      const studio=await import('/assets/studio.js'),form=document.querySelector('[data-form="content"]');
      await studio.studioSubmit(form,new FormData(form),'save');
    });
    assert.deepEqual(saved.steps.map(s=>s.key),['b1']);
    assert.equal(saved.steps[0].lesson_version_id,'lb');
    await racePage.close();
    console.log('PASS audit UI: delayed old editor cannot change or break saving the current path');

    const page=await browser.newPage();
    await prepare(page);
    await page.getByRole('link',{name:'Kelas',exact:true}).click();
    await page.locator('a[href="#/classes/page/100"]').click();
    await page.getByRole('heading',{name:'Target class',exact:true}).waitFor();
    await page.getByRole('link',{name:'Sebelumnya',exact:true}).waitFor();
    await page.goto(`${base}/#/studio`);
    await page.locator('a[href="#/studio/page/100"]').click();
    await page.getByRole('heading',{name:'Target class',exact:true}).waitFor();
    await page.locator('a[href="#/course/target/materials"]').click();
    await page.getByRole('heading',{name:'Target class',exact:true}).waitFor();
    assert.equal(await page.locator('.page-error').count(),0);
    console.log('PASS audit UI: class and Studio pagination, direct management beyond first 100 classes');

    await page.goto(`${base}/#/dashboard`);
    await page.getByRole('heading',{name:'Halo, Audit Teacher.',exact:true}).waitFor();
    assert.equal(await page.locator('.stat').filter({hasText:'Latihan berhasil'}).locator('strong').textContent(),'7');
    await page.setViewportSize({width:390,height:844});
    await page.goto(`${base}/#/studio`);
    await page.locator('a[href="#/studio/page/100"]').waitFor();
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.selectOption('#ui-locale','en');
    await page.getByRole('link',{name:'Next',exact:true}).waitFor();
    assert.deepEqual(errors,[]);
    console.log('PASS audit UI: persistent achievement counter, mobile layout and English paging');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error.stack||error.message);process.exitCode=1;});

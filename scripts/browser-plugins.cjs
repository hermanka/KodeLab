/* UI contract checks with mocked writes. No real plugin is installed by this test. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.env.TEST_BASE_URL || 'http://127.0.0.1:8000';
const revision='a'.repeat(64),newRevision='b'.repeat(64);
const user={id:'plugin-admin',username:'plugin_admin',full_name:'Plugin Admin',role:'admin'};
let installed=false,enabled=false,activeRevision=revision,savedProblem,uploads=0;
const errors=[];
const plugin=()=>({id:'sandbox-delegate',name:'Sandbox Delegate',description:'Plugin demo',enabled,active_revision:activeRevision,version:activeRevision===revision?'1.0.0':'2.0.0',versions:[{version:'1.0.0',revision},{version:'2.0.0',revision:newRevision}]});
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const page=await browser.newPage(); page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url()),p=url.pathname,method=request.method();
   if(p==='/' || p.startsWith('/assets/')) return route.continue();
   if(p==='/auth/me') return route.fulfill({json:user});
   if(p==='/my/stats') return route.fulfill({json:{accepted_exercises:0}});
   if(p==='/my/learning'||p==='/courses') return route.fulfill({json:[]});
   if(p==='/admin/judge-plugins'&&method==='GET') return route.fulfill({json:installed?[plugin()]:[]});
   if(p==='/admin/judge-plugins'&&method==='POST') {
    const body=request.postDataJSON(); assert.equal(body.trusted_code,true);
    assert.ok(Buffer.from(body.package_base64,'base64').equals(fs.readFileSync('plugin/examples/sandbox-delegate.zip')));
    installed=true; uploads++; return route.fulfill({status:201,json:plugin()});
   }
   if(p==='/admin/judge-plugins/sandbox-delegate'&&method==='PATCH') {
    const body=request.postDataJSON();enabled=body.enabled;activeRevision=body.revision;
    return route.fulfill({json:plugin()});
   }
   if(p==='/admin/judge-plugins/sandbox-delegate'&&method==='DELETE') {installed=false;return route.fulfill({json:{status:'uninstalled'}});}
   if(p==='/providers') return route.fulfill({json:{custom:{name:'custom',implemented:true,languages:['c17','cpp17']},...(enabled?{'sandbox-delegate':{name:'Sandbox Delegate',implemented:true,languages:['c17','cpp17'],version:'2.0.0'}}:{})}});
   if(p==='/courses/test-class') return route.fulfill({json:{id:'test-class',title:'Test',owner_id:user.id,can_manage:true,archived:false}});
   if(p==='/author/courses/test-class/problems'&&method==='POST') {
    savedProblem=request.postDataJSON(); return route.fulfill({status:201,json:{...savedProblem,id:'problem-v1',problem_id:'problem',revision:1,edit_revision:1,status:'draft'}});
   }
   if(p==='/author/problem-versions/problem-v1') return route.fulfill({json:{...savedProblem,id:'problem-v1',problem_id:'problem',revision:1,edit_revision:1,status:'draft'}});
   if(p==='/author/problem-versions/published-v1') return route.fulfill({json:{...savedProblem,provider:'custom',id:'published-v1',problem_id:'published-problem',revision:1,edit_revision:1,status:'published'}});
   if(p==='/author/problems/published-problem/versions'&&method==='POST') return route.fulfill({status:201,json:{id:'revised-v2'}});
   if(p==='/author/problem-versions/revised-v2') return route.fulfill({json:{...savedProblem,provider:'custom',id:'revised-v2',problem_id:'published-problem',revision:2,edit_revision:1,status:'draft'}});
   throw Error('Unexpected plugin UI request: '+method+' '+p);
  });
  await page.goto(base+'/#/admin/plugins');
  await page.getByRole('heading',{name:'Plugin penilaian',exact:true}).waitFor();
  assert.equal(await page.locator('#main-sidebar a[href="#/admin/plugins"]').count(),1);
  await page.locator('#plugin-package').setInputFiles('plugin/examples/sandbox-delegate.zip');
  await page.locator('form[data-form="install-plugin"] button[type="submit"]').click();
  assert.equal(uploads,0); // Native required checkbox guards installation.
  await page.locator('[name="trusted"]').check();
  await page.locator('form[data-form="install-plugin"] button[type="submit"]').click();
  await page.locator('[data-action="activate-plugin"]').waitFor();
  await page.locator('[data-action="activate-plugin"]').click();
  await page.locator('[data-action="deactivate-plugin"]').waitFor();
  assert.equal(enabled,true);
  await page.locator('#plugin-version-sandbox-delegate').selectOption(newRevision);
  await page.locator('[data-action="activate-plugin"]').click();
  await page.getByText('sandbox-delegate · v2.0.0',{exact:true}).waitFor();
  assert.equal(activeRevision,newRevision);
  console.log('PASS admin ZIP upload, explicit trust, activate, apply version');

  await page.evaluate(()=>location.hash='/problem-editor/new/test-class');
  await page.locator('#problem-provider').waitFor();
  await page.locator('#problem-provider').selectOption('sandbox-delegate');
  await page.locator('#content-title').fill('Plugin problem');
  await page.locator('#statement').fill('Add two numbers.');
  await page.locator('#reference-c17').fill('int main(){}');
  await page.locator('#reference-cpp17').fill('int main(){}');
  await page.locator('form[data-form="content"] button[type="submit"]').first().click();
  await page.waitForFunction(()=>location.hash.includes('/problem-editor/problem-v1/'));
  assert.equal(savedProblem.provider,'sandbox-delegate');
  console.log('PASS dynamic plugin selection and problem save');

  await page.evaluate(()=>location.hash='/problem-editor/published-v1/test-class');
  await page.getByRole('button',{name:'Ganti plugin melalui revisi',exact:true}).waitFor();
  assert.equal(await page.locator('#problem-provider').isDisabled(),true);
  await page.getByText('Plugin aktif: custom, Sandbox Delegate',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Ganti plugin melalui revisi',exact:true}).click();
  await page.waitForURL(/revised-v2/);
  await page.locator('#problem-provider').selectOption('sandbox-delegate');
  assert.equal(await page.locator('#problem-provider').isEnabled(),true);
  console.log('PASS published problem explains locked provider and opens editable revision');

  await page.evaluate(()=>location.hash='/admin/plugins');
  await page.locator('[data-action="deactivate-plugin"]').waitFor();
  await page.locator('[data-action="deactivate-plugin"]').click();
  await page.locator('[data-action="uninstall-plugin"]').waitFor();
  await page.locator('[data-action="uninstall-plugin"]').click();
  await page.locator('#modal [name="confirm"]').check();
  await page.locator('#modal button[type="submit"]').click();
  await page.getByText('Belum ada plugin tambahan.',{exact:true}).waitFor();
  assert.equal(installed,false);
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.locator('#ui-locale').selectOption('en');
  await page.getByRole('heading',{name:'Judging plugins',exact:true}).waitFor();
  assert.deepEqual(errors,[]);
  console.log('PASS deactivate/uninstall, mobile layout, English UI, no JS errors');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

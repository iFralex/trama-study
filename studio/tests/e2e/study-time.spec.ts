import {test,expect} from '@playwright/test';

test('local study estimates cover future chapters, explicit progress, settings and mobile',{tag:'@study-time'},async({page,request})=>{
 test.setTimeout(60000);
 test.skip(process.env.STUDIO_TIME_E2E!=='1','Requires the isolated study-time fixture');
 const boot=await (await request.get('/api/bootstrap')).json();expect(boot.courses.some((c:any)=>c.id==='curriculum-fixture-2026')).toBeTruthy();
 const paths=await (await request.get('/api/courses/curriculum-fixture-2026/paths')).json(),path=paths.find((p:any)=>!p.objective.archived);
 const data=await (await request.get('/api/paths/'+path.id)).json();
 // Keep the fixture deterministic across repeated runs.
 await request.post('/api/paths/'+path.id+'/study-time',{data:{daily_minutes:30,tracking:true,sid:data.sid}});
 await request.post('/api/sessions/'+data.sid+'/study-time/mark',{data:{chapter:'basics',version:data.current.version,block:'foundations',status:'todo'}});
 await page.addInitScript(()=>{localStorage.setItem('studio-last-view','corso');localStorage.setItem('studio-math-reading','text');});
 await page.route('**/*',async route=>route.fulfill({response:await route.fetch()}));
 let modelCalls=0;await page.route('**/api/sessions/*/chat',async route=>{modelCalls++;await route.abort();});
 await page.route('**/api/math-speech',route=>route.fulfill({json:{speech:'Formula del capitolo'}}));
 await page.goto('/',{waitUntil:'domcontentloaded'});
 await page.getByRole('combobox',{name:'IL TUO CORSO'}).selectOption('curriculum-fixture-2026');
 const times=page.locator('[aria-label="Tempo di studio del capitolo"]');await expect(times).toBeVisible();await expect(times).not.toContainText('Stima in preparazione');
 const section=page.getByLabel('Studio della sezione 1',{exact:true});
 await section.getByRole('button',{name:'Studiato',exact:true}).click();await expect(section.getByRole('button',{name:'Studiato',exact:true})).toHaveAttribute('aria-pressed','true');
 await page.reload({waitUntil:'domcontentloaded'});await page.getByRole('combobox',{name:'IL TUO CORSO'}).selectOption('curriculum-fixture-2026');await expect(page.getByLabel('Studio della sezione 1',{exact:true}).getByRole('button',{name:'Studiato',exact:true})).toHaveAttribute('aria-pressed','true');
 await page.getByLabel('Studio della sezione 1',{exact:true}).getByRole('button',{name:'Da rivedere',exact:true}).click();await expect(page.getByLabel('Studio della sezione 1',{exact:true}).getByRole('button',{name:'Da rivedere',exact:true})).toHaveAttribute('aria-pressed','true');
 await page.getByRole('navigation',{name:'Sezioni'}).getByRole('button',{name:'Percorso',exact:false}).click();
 const summary=page.getByRole('region',{name:'Tempo di studio del percorso'}).filter({visible:true});await expect(summary).toContainText('1 capitolo ancora da creare');
 await summary.getByText('Dettagli e ritmo di studio',{exact:true}).click();await summary.getByLabel('Minuti di studio al giorno',{exact:true}).fill('45');await summary.getByLabel('Rileva localmente il tempo in primo piano').uncheck();await summary.getByRole('button',{name:'Salva ritmo e rilevazione'}).click();await expect(summary).toContainText('45 min/giorno');
 await page.reload({waitUntil:'domcontentloaded'});await page.getByRole('combobox',{name:'IL TUO CORSO'}).selectOption('curriculum-fixture-2026');await page.getByRole('navigation',{name:'Sezioni'}).getByRole('button',{name:'Percorso',exact:false}).click();await expect(page.getByRole('region',{name:'Tempo di studio del percorso'}).filter({visible:true})).toContainText('45 min/giorno');
 await page.setViewportSize({width:390,height:844});await page.getByRole('navigation',{name:'Sezioni'}).getByRole('button',{name:'Studia',exact:false}).click();await expect(times).toBeVisible();
 const bounds=await times.boundingBox();expect(bounds!.x+bounds!.width).toBeLessThanOrEqual(391);
 await page.screenshot({path:'/private/tmp/studio-study-time-mobile.png'});
 expect(modelCalls).toBe(0);
});

import {test,expect} from '@playwright/test';
const course='curriculum-fixture-2026';
async function enter(page:any){const paths=await (await page.request.get('/api/courses/'+course+'/paths')).json();const ready=paths.find((p:any)=>p.objective.request==='Primo parziale di test: PRAM');await page.request.post('/api/paths/'+ready.id+'/open',{data:{fresh:true}});await page.goto('/');await page.locator('.course-label select').selectOption(course);await page.getByRole('button',{name:'Corso personale',exact:true}).click();await expect(page.locator('.course-status')).toBeVisible();await page.getByRole('combobox',{name:'Percorso',exact:true}).selectOption({label:'Primo parziale di test: PRAM'});await expect(page.getByRole('heading',{name:'PRAM dalle basi',exact:true})).toBeVisible();}
test.afterEach(async({request})=>{await request.post('/api/sessions',{data:{course:'a-course-2025-26'}});});

test('course chapters, sources, keyboard chat, diary and exact resume work together',async({page})=>{
  await enter(page);
  await expect(page.getByRole('navigation',{name:'Capitoli del corso'})).toBeVisible();
  await expect(page.getByText('Un algoritmo è una sequenza di passi.',{exact:false}).first()).toBeVisible();
  const chapter=page.getByLabel('Contenuto del capitolo'),chat=page.getByLabel('Messaggio al tutor del corso',{exact:true});
  const left=await chapter.boundingBox(),right=await chat.boundingBox();expect(right!.x).toBeGreaterThan(left!.x+left!.width);
  await chat.fill('Una bozza da conservare');await chat.focus();
  await page.waitForTimeout(2700);await expect(chat).toBeFocused();await expect(chat).toHaveValue('Una bozza da conservare');
  await chapter.evaluate(el=>{el.scrollTop=250;});
  await page.reload();await page.getByRole('button',{name:'Corso personale',exact:true}).click();
  await expect(chat).toHaveValue('Una bozza da conservare');await expect.poll(()=>chapter.evaluate(el=>el.scrollTop)).toBeGreaterThan(200);
  await page.getByRole('button',{name:'2. Riduzione parallela',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Riduzione parallela',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'1. PRAM dalle basi',exact:true}).click();
  await page.getByText('Diario e preferenze',{exact:true}).click();
  await page.getByLabel('Come preferisci studiare?').fill('Prima un esempio numerico, poi la formula.');
  await page.getByRole('button',{name:'Salva preferenza',exact:true}).click();
  await expect(page.locator('.course-note').filter({hasText:'Prima un esempio numerico, poi la formula.'}).first()).toBeVisible();
  await chapter.evaluate(el=>{el.scrollTop=0;});
  await page.locator('.course-block').first().getByRole('button',{name:'Fonte ↗'}).click();
  const source=page.getByRole('complementary',{name:'Fonte originale'});await expect(source).toBeVisible();
  await expect(source.locator('.pdf-page img')).toBeVisible();
  await page.getByRole('button',{name:'Chiudi fonte'}).click();
  await page.screenshot({path:'/private/tmp/studio-course-desktop.png',fullPage:true});
  await page.setViewportSize({width:740,height:950});
  await page.getByRole('button',{name:'Chat',exact:true}).click();await expect(chat).toBeVisible();
  await page.getByRole('button',{name:'Capitolo',exact:true}).click();await expect(chapter).toBeVisible();
});

test('course answers survive provider failure and the journal keeps facts and corrections',async({page})=>{
  await enter(page);
  const input=page.getByLabel('La tua risposta',{exact:true});await input.fill('2');
  await page.getByRole('button',{name:'Verifica risposta',exact:true}).click();
  await expect(page.getByText('VALUTAZIONE PROVVISORIA',{exact:true})).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('Seleziona un modello disponibile');
  await page.getByRole('button',{name:'Un indizio',exact:true}).click();
  await expect(page.getByText('Ogni livello dimezza i valori.',{exact:true})).toBeVisible();
  await input.fill('3');await page.getByRole('button',{name:'Verifica risposta',exact:true}).click();
  await expect(page.getByText('Tentativo con 1 aiuti.',{exact:true})).toBeVisible();
  await page.getByText('Diario e preferenze',{exact:true}).click();
  const fact=page.locator('.course-note').filter({hasText:'Risposta consegnata'}).first();await expect(fact).toBeVisible();
  await fact.getByText('Correggi questa nota',{exact:true}).click();await fact.getByLabel('La tua correzione').fill('La prima risposta era un errore di digitazione.');
  await fact.getByRole('button',{name:'Salva correzione',exact:true}).click();
  await expect(fact).toContainText('Correzione: La prima risposta era un errore di digitazione.');
  await page.reload();await page.getByRole('button',{name:'Corso personale',exact:true}).click();
  await expect(input).toHaveValue('3');
});

test('new exam scope is editable and a missing provider does not lose the request',async({page,request})=>{
  await enter(page);await page.getByRole('button',{name:'Nuovo obiettivo d’esame',exact:true}).click();
  await expect(page.getByText('Nessun tema viene preselezionato prima di conoscere il tuo obiettivo.',{exact:false})).toBeVisible();
  await expect(page.locator('.course-setup input[type=checkbox]')).toHaveCount(0);
  await page.getByLabel('Obiettivo e argomenti').fill('Esame completo: tutti gli argomenti, escluso il progetto.');
  await page.getByRole('button',{name:'Prepara la scheda dell’esame',exact:true}).click();
  await expect(page.getByText('I risultati già salvati restano disponibili.',{exact:false})).toBeVisible();
  const saved=await (await request.get('/api/courses/'+course+'/paths')).json();
  expect(saved[0].objective.request).toContain('Esame completo');expect(saved[0].objective.confirmed).toBe(false);
  const detail=await (await request.get('/api/paths/'+saved[0].id)).json();
  expect(detail.coverage.every((d:any)=>d.total===0)).toBe(true);
  expect(detail.objective.reserved_requested).toEqual([]);
});

test('a queued activity save never erases the next course chat draft',async({page})=>{
  await enter(page);
  let finishSave!:()=>void,finishReply!:()=>void;
  const saved=new Promise<void>(resolve=>finishSave=resolve),reply=new Promise<void>(resolve=>finishReply=resolve);
  await page.route('**/api/sessions/*/events',async route=>{await saved;await route.continue();});
  await page.route('**/api/sessions/*/chat',async route=>{await reply;await route.fulfill({contentType:'text/event-stream',body:'data: '+JSON.stringify({type:'delta',text:'Una spiegazione breve.'})+'\n\n'});});
  await page.getByLabel('La tua risposta',{exact:true}).fill('2');
  const chat=page.getByLabel('Messaggio al tutor del corso',{exact:true});
  await chat.fill('Prima domanda.');await page.getByRole('button',{name:'Invia messaggio al tutor del corso',exact:true}).click();
  await chat.fill('La prossima domanda, da conservare.');await chat.focus();finishSave();finishReply();
  await expect(page.getByRole('button',{name:'Invia messaggio al tutor del corso',exact:true})).toBeVisible();
  await expect(chat).toBeFocused();await expect(chat).toHaveValue('La prossima domanda, da conservare.');
  await page.reload();await expect(chat).toHaveValue('La prossima domanda, da conservare.');
});

import {test,expect} from '@playwright/test';
const course='selective-course-2026';
async function enter(page:any){await page.goto('/');await page.locator('.course-label select').selectOption(course);await page.getByRole('button',{name:'Corso personale',exact:true}).click();await page.getByRole('combobox',{name:'Percorso',exact:true}).selectOption({label:'Primo parziale PRAM'});await expect(page.getByRole('heading',{name:'PRAM dalle basi',exact:true})).toBeVisible();}

test('selective sources, complete reviews and autosaved choices are accessible without focus changes',async({page})=>{
  await enter(page);
  await expect(page.getByLabel('Preparazione dalle fonti originali')).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByText('Doppia revisione completata',{exact:false})).toBeVisible();
  await page.getByText('Fonti selezionate, lezioni ed esclusioni',{exact:true}).click();
  await page.getByText('2026-09-16 · Lezione',{exact:false}).click();
  const select=page.locator('.preparation-decision select').first();await expect(select).toBeVisible();await select.focus();
  await page.waitForTimeout(2800);await expect(select).toBeFocused();
  await select.selectOption('outside');await expect(select).toHaveValue('outside');
  await page.reload();await page.getByRole('button',{name:'Corso personale',exact:true}).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await page.getByText('Fonti selezionate, lezioni ed esclusioni',{exact:true}).click();await page.getByText('2026-09-16 · Lezione',{exact:false}).click();
  await expect(page.locator('.preparation-decision select').first()).toHaveValue('outside');
  await page.screenshot({path:'/private/tmp/studio-selective-desktop.png',fullPage:true});
  await page.setViewportSize({width:740,height:950});await page.getByRole('button',{name:'Chat',exact:true}).click();
  const chat=page.getByLabel('Messaggio al tutor del corso',{exact:true});await chat.fill('Una domanda da conservare');await chat.press('Shift+Enter');await expect(chat).toHaveValue('Una domanda da conservare\n');
});

test('archived outputs are marked and a student clarification remains stored after provider failure',async({page,request})=>{
  await enter(page);
  await expect(page.getByRole('combobox',{name:'Percorso',exact:true})).toContainText('Archivio · Analisi storica da non riusare');
  const note=page.getByLabel('Chiarimento per il tutor');await note.fill('Il docente usa P per il numero dei processori.');
  await page.getByRole('button',{name:'Salva e richiedi revisione',exact:true}).click();
  await expect(page.getByText('Il tuo chiarimento: Il docente usa P per il numero dei processori.',{exact:true})).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('Seleziona un modello disponibile');
  const paths=await (await request.get('/api/courses/'+course+'/paths')).json();const active=paths.find((p:any)=>!p.objective.archived);
  const detail=await (await request.get('/api/paths/'+active.id)).json();expect(detail.preparation.issues[0].data.student_note).toContain('numero dei processori');
});

test('scope followup keeps its draft and reopens source verification without confirming the objective',async({page,request})=>{
  const response=await request.post('/api/paths',{data:{course,request:'Primo parziale: verifica argomenti dubbi',reserved:[]}});
  expect(response.ok()).toBeTruthy();const fresh=await response.json();let submitted=false;
  await page.route('**/api/paths/'+fresh.id,async route=>{
    const result=await route.fetch();const data=await result.json();
    if(!submitted){data.status='clarification';data.objective.clarification='OpenMP incluso?';data.objective.summary='Confine da verificare';data.objective.included=['PRAM'];}
    await route.fulfill({response:result,json:data});
  });
  await page.goto('/');await page.locator('.course-label select').selectOption(course);
  await page.getByRole('button',{name:'Corso personale',exact:true}).click();
  await page.getByRole('combobox',{name:'Percorso',exact:true}).selectOption(fresh.id);
  const input=page.getByLabel('Indicazioni per il tutor',{exact:true});
  await input.fill('Controlla i parziali precedenti e i singoli quesiti delle prove complete.');
  await page.reload();await page.getByRole('button',{name:'Corso personale',exact:true}).click();
  await expect(input).toHaveValue('Controlla i parziali precedenti e i singoli quesiti delle prove complete.',{timeout:15000});
  const sent=page.waitForResponse(r=>r.url().endsWith('/scope-followup')&&r.request().method()==='POST');
  submitted=true;await page.getByRole('button',{name:'Verifica e aggiorna il perimetro',exact:true}).click();
  expect((await sent).ok()).toBeTruthy();
  await expect(page.getByRole('alert')).toContainText('Seleziona un modello disponibile');
  const saved=await (await request.get('/api/paths/'+fresh.id)).json();
  expect(saved.objective.confirmed).toBe(false);expect(saved.objective.scope_followups[0]).toContain('singoli quesiti');
  expect(saved.objective.reserved_requested).toEqual([]);
});

test('model assignment and expert handoff update without stealing the chat focus',async({page,request})=>{
  const paths=await (await request.get('/api/courses/'+course+'/paths')).json();const target=paths.find((p:any)=>p.objective.summary==='Primo parziale PRAM');
  let active='gpt-6-luna';
  await page.route('**/api/paths/'+target.id,async route=>{const response=await route.fetch();const data=await response.json();data.preparation.current_task={...data.preparation.current_task,routing:{primary:{id:'gpt-6-luna'},active:{id:active},reason:'Lettura strutturata',escalation_reason:active==='gpt-6.1-sol'?'Verifica di una fonte ambigua':null}};await route.fulfill({response,json:data});});
  await enter(page);await expect(page.locator('.preparation-progress')).toContainText('gpt-6-luna');
  const chat=page.getByLabel('Messaggio al tutor del corso',{exact:true});await chat.fill('Bozza durante il cambio di modello');await chat.focus();active='gpt-6.1-sol';
  await expect(page.locator('.preparation-progress')).toContainText('Verifica di una fonte ambigua',{timeout:8000});
  await expect(chat).toBeFocused();await expect(chat).toHaveValue('Bozza durante il cambio di modello');
});

test('automatic model assignment can be enabled from model settings',async({page})=>{
  await page.route('**/api/models',route=>route.fulfill({json:{models:[{provider:'openai',id:'gpt-6.1-sol',name:'GPT-6.1 Sol'},{provider:'openai',id:'gpt-6-luna',name:'GPT-6 Luna'}],providers:[],selected:{provider:'openai',id:'gpt-6.1-sol'},routing:{enabled:false}}}));
  let saved:any;
  await page.route('**/api/model-routing',async route=>{saved=route.request().postDataJSON();await route.fulfill({json:{saved:true,routing:{enabled:saved.enabled}}});});
  await page.goto('/');await page.getByRole('button',{name:'◇ Modello e accesso'}).click();
  const toggle=page.getByRole('checkbox',{name:'Assegnazione automatica Luna/Sol'});await expect(toggle).not.toBeChecked();await toggle.click();await expect(toggle).toBeChecked();expect(saved).toEqual({enabled:true});
});

test('compact map progress updates without moving focus or losing the chat draft',async({page,request})=>{
  const paths=await (await request.get('/api/courses/'+course+'/paths')).json();const target=paths.find((p:any)=>p.objective.summary==='Primo parziale PRAM');
  let integrated=172,parts=0;
  await page.route('**/api/paths/'+target.id,async route=>{
    const response=await route.fetch(),data=await response.json();data.status='running';
    data.preparation.phase='map_contribution';data.preparation.mapping={integrated,total:886,parts_done:parts};
    await route.fulfill({response,json:data});
  });
  await enter(page);await expect(page.getByRole('heading',{name:'Contributi alla mappa',exact:true})).toBeVisible();
  await expect(page.locator('.preparation-progress')).toContainText('172 / 886 evidenze organizzate');
  const chat=page.getByLabel('Messaggio al tutor del corso',{exact:true});await chat.fill('La mia bozza rimane qui');await chat.focus();
  integrated=230;parts=1;
  await expect(page.locator('.preparation-progress')).toContainText('230 / 886 evidenze organizzate',{timeout:8000});
  await expect(chat).toBeFocused();await expect(chat).toHaveValue('La mia bozza rimane qui');
});

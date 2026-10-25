import {test,expect,type Page} from '@playwright/test';

async function fixture(page:Page,options:{openAnswer?:boolean}={}){
  const formula=String.raw`F=(a_0\land b_0)\lor(a_1\land b_1)\lor(a_2\land b_2)\lor(a_3\land b_3).`;
  const activity={id:'boolean-activity',version:1,state:{},created:'2026-01-01',spec:{kind:'completion',title:"Completa l'aggregazione booleana",prompt:'Calcola\n\n$$'+formula+'$$\n\nLe coppie di input occupano otto celle distinte.',curriculum:{chapter:'boolean'},origin:'generated',sources:['passage-1']}};
  const session:any={session:{id:'workspace-session',mode:'learn',minutes:25,goal:'Test',course:'workspace-course',current:activity.id},curriculum:{path:'workspace-path'},activities:[activity],messages:[],attempts:[],progress:[]};
  const path:any={id:'workspace-path',sid:session.session.id,status:'ready',objective:{request:'Primo parziale',summary:'Primo parziale',included:['PRAM'],engine:2},coverage:[],plan:{version:1,data:{final:true}},chapters:[{id:'boolean',title:'PRAM e aggregazione',objective:'Comprendere gli accessi concorrenti.',ready:true,version:1},{id:'reduction',title:'Riduzione parallela',ready:true,version:1}],position:{chapter:'boolean',block:'intro'},current:{chapter:'boolean',version:1,content:{review:true,blocks:[{id:'intro',kind:'text',text:'Un algoritmo combina passi elementari. Seleziona questa frase per discuterne.\n\nIl costo è $T(n)=an+b$.\n\n'+('Un esempio concreto da leggere.\n\n'.repeat(12)),sources:['passage-1']},{id:'exercise',kind:'activity',activity:activity.id,activity_version:1},{id:'conclusion',kind:'text',text:'Ora confronta i due procedimenti.',sources:[]}]}},profile:{total:0,formats:{},questions:[]},recalls:[],journal:[],revisions:[],reservations:[]};
  const state={path,session,reads:0,chats:[] as string[],searches:[] as string[]};
  await page.addInitScript(()=>{localStorage.setItem('studio-last-view','corso');localStorage.setItem('studio-math-reading','text');});
  await page.route('**/*',async route=>{
    if(new URL(route.request().url()).pathname.startsWith('/api/'))return route.fallback();
    await route.fulfill({response:await route.fetch()});
  });
  await page.route('**/api/**',async route=>{
    const request=route.request(),url=new URL(request.url()),pathname=url.pathname;
    let data:unknown={};
    if(pathname==='/api/bootstrap')data={selected:'workspace-course',courses:[{id:'workspace-course',label:'Parallel Computing'}]};
    else if(pathname.endsWith('/inventory'))data={documents:[{id:'doc-1',title:'Slide PRAM',exam:false}],proposed:[]};
    else if(pathname.endsWith('/paths'))data=[path];
    else if(pathname==='/api/paths/workspace-path'){state.reads++;data=path;}
    else if(pathname.endsWith('/position')){path.position.block=request.postDataJSON().block;}
    else if(pathname.endsWith('/chapter')){path.current.chapter=request.postDataJSON().chapter;path.position.chapter=path.current.chapter;path.position.block='intro';data=session;}
    else if(pathname.endsWith('/events')){
      const event=request.postDataJSON();
      if(event.kind==='submit'){const attempt={id:'attempt-1',activity:activity.id,version:1,grade:{status:'provisional',correct:options.openAnswer?null:false,feedback:options.openAnswer?'Risposta salvata. La valutazione aperta richiede il tutor o una tua autovalutazione.':'Rivedi quali processori propongono il valore 1.'}};session.attempts=[attempt];data={attempt};}
      else{activity.state={...activity.state,...event.payload};}
    }
    else if(pathname.endsWith('/chat')){
      state.chats.push(request.postDataJSON().text);
      session.messages.push({id:'reply-'+state.chats.length,role:'assistant',text:'Consideriamo il passaggio selezionato.',created:'2026-01-02'});
      return route.fulfill({contentType:'text/event-stream',body:'data: '+JSON.stringify({type:'delta',text:'Consideriamo il passaggio selezionato.'})+'\n\n'});
    }
    else if(pathname==='/api/sessions/workspace-session/materials')data=[{id:'doc-1',path:'corsi/workspace-course/slide/PRAM.pdf',kind:'pdf',passages:2}];
    else if(pathname.endsWith('/materials/doc-1'))data={document:'doc-1',total_lines:1,lines:[{line:1,text:'Letture esclusive e scritture concorrenti.',source:'passage-1',page:2}]};
    else if(pathname.endsWith('/search')){state.searches.push(url.searchParams.get('q')??'');data=[{id:'passage-1',title:'Slide PRAM',kind:'notebook',page:2,text:'Letture esclusive e scritture concorrenti.'}];}
    else if(pathname.includes('/sources/'))data={id:'passage-1',title:'Slide PRAM',kind:'notebook',page:2,text:'Letture esclusive e scritture concorrenti.',quality:'Fonte originale'};
    else if(pathname==='/api/history')data=[{id:session.session.id,goal:'Conversazione precedente',updated:'2026-01-01',messages:2,mode:'learn'}];
    else if(pathname.endsWith('/open')||pathname==='/api/sessions/workspace-session'||pathname==='/api/sessions')data=session;
    else if(pathname==='/api/math-speech')data={speech:request.postDataJSON().tex.startsWith('F=')?'F uguale a quattro termini booleani combinati con oppure.':'T di n uguale a a per n più b'};
    await route.fulfill({json:data});
  });
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'PRAM e aggregazione',exact:true}).last()).toBeVisible();
  return state;
}

test('reading, optional tools, source references and mobile preserve the chapter position and drafts',async({page})=>{
  await fixture(page);
  await expect(page.getByRole('navigation',{name:'Sezioni'}).getByRole('button')).toHaveText(['▤Studia','≡Percorso','↻Allenamento','↗Fonti']);
  await expect(page.getByLabel('Strumenti di studio')).toBeHidden();
  await page.getByRole('button',{name:'Continua a studiare'}).click();
  const chapter=page.getByLabel('Contenuto del capitolo');
  await expect(chapter).toBeFocused();
  await page.getByRole('button',{name:'☰ Indice',exact:true}).click();
  await expect(page.getByRole('navigation',{name:'Capitoli del corso'})).toBeVisible();
  await page.getByLabel('Mantieni aperto su desktop').check();
  await page.getByRole('button',{name:'☰ Indice',exact:true}).click();
  await expect(page.getByRole('navigation',{name:'Capitoli del corso'})).toBeHidden();
  await page.getByRole('button',{name:'Tutor',exact:true}).click();
  const draft=page.getByLabel('Messaggio al tutor del corso',{exact:true});
  await draft.fill('Una domanda da conservare');
  const separator=page.getByRole('separator',{name:'Larghezza pannello'});await separator.focus();await separator.press('ArrowLeft');
  await expect(separator).toHaveAttribute('aria-valuenow','400');
  await page.getByRole('tab',{name:'Cronologia'}).click();
  await expect(page.getByText('Conversazione precedente',{exact:true})).toBeVisible();
  await page.getByRole('tab',{name:'Tutor',exact:true}).click();await expect(draft).toHaveValue('Una domanda da conservare');
  await page.getByRole('button',{name:'Torna al capitolo',exact:true}).click();
  await chapter.evaluate(el=>{el.scrollTop=220;});
  await page.waitForTimeout(600);
  await page.getByRole('button',{name:'Fonte 1 ↗',exact:true}).first().click();
  await expect(page.getByLabel('Fonte originale')).toBeVisible();
  await expect(page.locator('.source-embedded')).toBeVisible();
  await page.getByRole('button',{name:'Chiudi fonte'}).click();
  await page.getByRole('button',{name:'Torna al capitolo',exact:true}).click();
  await page.setViewportSize({width:390,height:844});
  const before=await chapter.evaluate(el=>el.scrollTop);
  await page.getByRole('button',{name:'Tutor',exact:true}).click();
  await expect(draft).toHaveValue('Una domanda da conservare');
  const box=await page.getByLabel('Strumenti di studio').boundingBox();expect(box?.width).toBe(390);
  await page.getByRole('button',{name:'Torna al capitolo',exact:true}).click();
  expect(await chapter.evaluate(el=>el.scrollTop)).toBe(before);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.screenshot({path:'/private/tmp/studio-workspace-mobile.png',fullPage:true});
});

test('background revisions are offered without replacing the chapter until requested',async({page})=>{
  const state=await fixture(page);
  const original='Un algoritmo combina passi elementari.';
  await expect(page.getByLabel('Contenuto del capitolo')).toContainText(original);
  state.path.current.content.blocks[0].text='Una spiegazione aggiornata, disponibile su richiesta.';
  await expect(page.getByRole('button',{name:'Aggiornamento disponibile · Applica'})).toBeVisible({timeout:8000});
  await expect(page.getByLabel('Contenuto del capitolo')).toContainText(original);
  await expect(page.getByLabel('Contenuto del capitolo')).not.toContainText('Una spiegazione aggiornata');
  await page.getByRole('button',{name:'Aggiornamento disponibile · Applica'}).click();
  await expect(page.getByLabel('Contenuto del capitolo')).toContainText('Una spiegazione aggiornata');
});

test('selected prose becomes visible tutor context and exercises retain inline feedback',async({page})=>{
  const state=await fixture(page);
  await page.getByRole('button',{name:'Continua a studiare'}).click();
  const chapter=page.getByLabel('Contenuto del capitolo');
  await chapter.locator('.course-block p').first().evaluate(el=>{const range=document.createRange();range.selectNodeContents(el);window.getSelection()!.removeAllRanges();window.getSelection()!.addRange(range);el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));});
  await expect(page.getByLabel('Chiedi sul testo selezionato')).toBeVisible();
  await page.getByRole('button',{name:'Spiegami questo',exact:true}).click();
  await expect.poll(()=>state.chats.length).toBe(1);
  expect(state.chats[0]).toContain('Un algoritmo combina passi elementari.');
  await expect(page.locator('.discussion-context')).toContainText('Un algoritmo combina passi elementari.');
  await page.getByRole('button',{name:'Torna al capitolo',exact:true}).click();
  const activity=page.locator('[data-activity-id="boolean-activity"]');
  await activity.getByLabel('La tua risposta',{exact:true}).fill('Scrivono i processori con termine vero.');
  await activity.getByRole('button',{name:'Verifica risposta',exact:true}).click();
  await expect(activity.getByLabel('Riscontro sulla risposta')).toContainText('Rivedi quali processori');
  await expect(activity.getByLabel('Riscontro sulla risposta')).toContainText('Prossimo passo');
  await page.reload();
  await expect(page.locator('[data-activity-id="boolean-activity"]')).toBeVisible({timeout:15000});
  await expect(page.locator('[data-activity-id="boolean-activity"]').getByLabel('La tua risposta',{exact:true})).toHaveValue('Scrivono i processori con termine vero.');
});

test('path and training have dedicated views and return to the same study position',async({page})=>{
  await fixture(page);
  await page.getByRole('button',{name:'Continua a studiare'}).click();
  const chapter=page.getByLabel('Contenuto del capitolo');await chapter.evaluate(el=>{el.scrollTop=200;});await page.waitForTimeout(600);
  await page.getByRole('button',{name:'Percorso',exact:true}).click();
  await expect(page.locator('.chapter-grid')).toBeVisible();
  await expect(page.getByText('Diario e preferenze',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Allenamento',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Ripassi a distanza'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Simulazioni d’esame'})).toBeVisible();
  await page.getByRole('button',{name:'Studia',exact:true}).click();
  await expect.poll(()=>chapter.evaluate(el=>el.scrollTop)).toBeGreaterThan(150);
  await page.screenshot({path:'/private/tmp/studio-workspace-desktop.png',fullPage:true});
});


test('original materials can be browsed by folder and opened at their source',async({page})=>{
  await fixture(page);
  await page.getByRole('navigation',{name:'Sezioni'}).getByRole('button',{name:'Fonti',exact:true}).click();
  await expect(page.getByLabel('Archivio dei materiali')).toBeVisible();
  await page.getByRole('button',{name:/PRAM.pdf/}).click();
  await expect(page.locator('.material-preview')).toContainText('Letture esclusive e scritture concorrenti.');
  await page.getByRole('button',{name:'Apri la fonte originale ↗',exact:true}).click();
  await expect(page.getByLabel('Fonte originale')).toContainText('Slide PRAM');
});


test('open answers show automatic correction in progress and replace it with the saved assessment',async({page})=>{
  const state=await fixture(page,{openAnswer:true});
  let finish!:()=>void;const waiting=new Promise<void>(resolve=>finish=resolve);
  await page.route('**/api/sessions/*/chat',async route=>{
    await waiting;const attempt=state.session.attempts[0];
    attempt.grade={status:'provisional',correct:true,feedback:'Il ragionamento è corretto: scrivono solo i processori con termine vero.',previous:attempt.grade};
    await route.fulfill({contentType:'text/event-stream',body:'data: '+JSON.stringify({type:'delta',text:'Confrontiamo il tuo ragionamento con la regola Common.'})+'\n\n'});
  });
  const activity=page.locator('[data-activity-id="boolean-activity"]');
  await activity.getByLabel('La tua risposta',{exact:true}).fill('Scrivono solo i processori con termine vero.');
  await activity.getByRole('button',{name:'Verifica risposta',exact:true}).click();
  const feedback=activity.getByLabel('Riscontro sulla risposta');
  await expect(feedback).toContainText('CORREZIONE IN CORSO');
  await expect(feedback).toContainText('Il riscontro comparirà qui automaticamente.');
  await expect(feedback).not.toContainText('Prossimo passo');
  await expect(feedback).not.toContainText('richiede il tutor o una tua autovalutazione');
  await expect(feedback.getByRole('button',{name:'Chiedi la correzione al tutor'})).toHaveCount(0);
  finish();
  await expect(feedback).toContainText('VALUTAZIONE DEL TUTOR · PROVVISORIA');
  await expect(feedback).toContainText('Il ragionamento è corretto');
  await expect(feedback).not.toContainText('CORREZIONE IN CORSO');
  await expect(feedback).toContainText('Prossimo passo');
});

test('failed correction keeps the answer and offers a tracked retry beside the exercise',async({page})=>{
  const state=await fixture(page,{openAnswer:true});
  await page.route('**/api/sessions/*/chat',route=>route.fulfill({status:503,json:{error:'Provider temporaneamente non disponibile.'}}));
  const activity=page.locator('[data-activity-id="boolean-activity"]');
  const answer=activity.getByLabel('La tua risposta',{exact:true});await answer.fill('La mia risposta resta salvata.');
  await activity.getByRole('button',{name:'Verifica risposta',exact:true}).click();
  const feedback=activity.getByLabel('Riscontro sulla risposta');
  await expect(feedback).toContainText('CORREZIONE NON COMPLETATA');
  await expect(feedback).toContainText('La risposta è salvata.');
  await expect(feedback).not.toContainText('Prossimo passo');
  await expect(answer).toHaveValue('La mia risposta resta salvata.');
  await page.route('**/api/sessions/*/assess',async route=>{const attempt=state.session.attempts[0];attempt.grade={status:'provisional',correct:null,feedback:'Serve precisare quali processori scrivono.',previous:attempt.grade};await route.fulfill({json:attempt.grade});});
  await feedback.getByRole('button',{name:'Riprova la correzione',exact:true}).click();
  await expect(feedback).toContainText('Serve precisare quali processori scrivono.');
  await expect(feedback).toContainText('VALUTAZIONE DEL TUTOR · PROVVISORIA');
  await expect(feedback).not.toContainText('CORREZIONE NON COMPLETATA');
});

test('a tutor explanation appears inline even when no structured assessment was saved',async({page})=>{
  await fixture(page,{openAnswer:true});
  const activity=page.locator('[data-activity-id="boolean-activity"]');
  await activity.getByLabel('La tua risposta',{exact:true}).fill('La mia spiegazione.');
  await activity.getByRole('button',{name:'Verifica risposta',exact:true}).click();
  const feedback=activity.getByLabel('Riscontro sulla risposta');
  await expect(feedback).toContainText('RISCONTRO DEL TUTOR');
  await expect(feedback).toContainText('Consideriamo il passaggio selezionato.');
  await expect(feedback).not.toContainText('richiede il tutor o una tua autovalutazione');
  await expect(feedback).not.toContainText('rivedi il ragionamento usando il riscontro e prova di nuovo');
});


test('a failed view refresh after submission reports the saved answer without leaving correction pending',async({page})=>{
  await fixture(page,{openAnswer:true});
  let fail=true;
  await page.route('**/api/sessions/workspace-session',async route=>{if(fail){fail=false;await route.fulfill({status:503,json:{error:'Aggiornamento temporaneamente non disponibile.'}});}else await route.fallback();});
  const activity=page.locator('[data-activity-id="boolean-activity"]');
  await activity.getByLabel('La tua risposta',{exact:true}).fill('La risposta è sul disco.');
  await activity.getByRole('button',{name:'Verifica risposta',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Risposta salvata');
  await expect(activity.getByLabel('Riscontro sulla risposta')).toContainText('CORREZIONE NON COMPLETATA',{timeout:8000});
  await expect(activity.getByRole('button',{name:'Riprova la correzione',exact:true})).toBeEnabled();
});

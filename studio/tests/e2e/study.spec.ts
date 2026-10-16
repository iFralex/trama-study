import {test,expect} from '@playwright/test';

test('real pathway, hints, HTML interaction, resume, sources and recall',async({page,request})=>{
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/');
  await page.getByRole('button',{name:'Inizia una nuova sessione'}).click();
  await expect(page.getByRole('heading',{name:'Prima di iniziare'})).toBeVisible();
  await page.getByRole('radio',{name:'EREW',exact:true}).check();
  await page.getByRole('button',{name:'Verifica risposta',exact:true}).click();
  await expect(page.getByText('Non ancora. Controlla le ipotesi e riprova.')).toBeVisible();
  await page.getByRole('button',{name:'Un indizio',exact:true}).click();
  await expect(page.getByText('Separa il vincolo sulle letture da quello sulle scritture.')).toBeVisible();
  await page.getByRole('radio',{name:'CREW',exact:true}).check();
  await page.getByRole('button',{name:'Verifica risposta',exact:true}).click();
  await expect(page.getByText('Tentativo con 1 aiuti.')).toBeVisible();
  await page.getByRole('button',{name:'Passa al prossimo passo →'}).click();
  await page.getByRole('button',{name:'Continua',exact:true}).click();
  await page.getByLabel('La tua risposta', {exact:true}).fill('3');
  await page.getByRole('button',{name:'Verifica risposta',exact:true}).click();
  await page.getByRole('button',{name:'Passa al prossimo passo →'}).click();
  const frame=page.frameLocator('iframe.artifact');
  await frame.getByRole('combobox',{name:'Processori',exact:true}).selectOption('2');
  await frame.getByRole('button',{name:'Avanza di un livello'}).click();
  await expect(frame.locator('#summary')).toContainText('passi ideali: 2');
  await page.reload();await page.getByRole('button',{name:'Riprendi il percorso →'}).click();
  await expect(frame.getByRole('combobox',{name:'Processori',exact:true})).toHaveValue('2');
  await expect(frame.locator('#summary')).toContainText('Livello 1/3');
  await frame.getByRole('combobox',{name:'Algoritmo',exact:true}).selectOption('scan');
  await frame.getByRole('combobox',{name:'Modello',exact:true}).selectOption('EREW');
  await expect(frame.getByRole('button',{name:'Avanza di un livello'})).toBeDisabled();
  await expect(frame.locator('#error')).toContainText('non è valido');
  await frame.getByRole('combobox',{name:'Modello',exact:true}).selectOption('CREW');
  for(let i=0;i<3;i++)await frame.getByRole('button',{name:'Avanza di un livello'}).click();
  await expect(frame.locator('#array')).toHaveText('1361015212836');
  await page.getByRole('button',{name:'Metti alla prova quello che hai osservato'}).click();
  await page.getByLabel('La tua risposta', {exact:true}).fill('old[i]+old[i-d]');
  await page.getByRole('button',{name:'Verifica risposta',exact:true}).click();
  await page.getByRole('button',{name:'Passa al prossimo passo →'}).click();
  await expect(page.getByText('Domanda da un tema originale · criteri proposti')).toBeVisible();
  await page.getByLabel('La tua risposta', {exact:true}).fill('EREW: exclusive reads and writes. CREW: concurrent reads, exclusive writes. CRCW: both concurrent, common rule.');
  await page.getByRole('button',{name:'Verifica risposta',exact:true}).click();
  await expect(page.getByText('VALUTAZIONE PROVVISORIA',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Passa al prossimo passo →'}).click();
  await page.getByLabel('La tua risposta', {exact:true}).fill('8');
  await page.getByRole('button',{name:'Verifica risposta',exact:true}).click();
  await expect(page.getByText('Corretto. Ora prova a spiegare perché.')).toBeVisible();
  await page.getByRole('button',{name:'Ripassi',exact:true}).click();
  await page.getByRole('button',{name:'Mettimi alla prova →'}).nth(1).click();
  await expect(page.getByRole('heading',{name:'Richiamo · un caso nuovo'})).toBeVisible();
  await page.getByRole('button',{name:'Fonti',exact:true}).click();
  await page.getByLabel('Cerca nelle fonti').fill('riduzione');
  await page.getByRole('button',{name:'Cerca',exact:true}).click();
  await page.locator('.search-result').first().click();
  await expect(page.getByRole('complementary',{name:'Fonte originale'})).toBeVisible();
  const pdf=page.locator('.pdf-page img');
  if(await pdf.count()){const url=await pdf.getAttribute('src');const response=await request.get(url!);expect(response.status()).toBe(200);expect(response.headers()['content-type']).toContain('image/png');await expect(pdf).toBeVisible();const original=page.getByRole('link',{name:/Apri il PDF originale/});expect(await original.getAttribute('href')).toContain('#page=');}
  await page.screenshot({path:process.env.STUDIO_SHOT_DIR?process.env.STUDIO_SHOT_DIR+'/sources.png':'test-results/sources.png',fullPage:true});
  expect(errors).toEqual([]);
});

test('keyboard, provider failure preservation, source isolation and exam',async({page})=>{
  await page.goto('/');await page.getByRole('button',{name:'Inizia una nuova sessione'}).click();
  const composer=page.getByLabel('Messaggio al tutor');await composer.fill('Spiegami PRAM usando le fonti.');
  await page.getByRole('button',{name:'Invia messaggio'}).click();
  await expect(page.getByRole('alert')).toContainText('Seleziona un modello disponibile');
  await expect(page.locator('.message.user')).toContainText('Spiegami PRAM');
  await page.getByRole('button',{name:'◇ Modello e accesso'}).click();
  const dialog=page.getByRole('dialog');await expect(dialog).toBeVisible();
  await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button',{name:'◇ Modello e accesso'})).toBeFocused();
  await page.getByRole('button',{name:'Simulazione autonoma',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Prova autonoma · tema riservato'})).toBeVisible();
  await expect(composer).toBeDisabled();await expect(page.getByRole('button',{name:'Un indizio',exact:true})).toHaveCount(0);
  await page.getByLabel('La tua risposta',{exact:true}).fill('A saved independent answer.');
  await page.getByRole('button',{name:'Consegna',exact:true}).click();
  await expect(page.getByText('VALUTAZIONE PROVVISORIA',{exact:true})).toBeVisible();
  await page.screenshot({path:process.env.STUDIO_SHOT_DIR?process.env.STUDIO_SHOT_DIR+'/exam.png':'test-results/exam.png',fullPage:true});
});

test('a response never steals composer focus or overwrites the next draft',async({page,request})=>{
  await page.goto('/');await page.getByRole('button',{name:'Inizia una nuova sessione'}).click();
  let release!:()=>void;const wait=new Promise<void>(resolve=>release=resolve);
  await page.route('**/api/sessions/*/chat',async route=>{
    const url=route.request().url().replace(/\/chat$/,'');const view=await (await request.get(url)).json();
    await wait;
    await route.fulfill({contentType:'text/event-stream',body:'data: '+JSON.stringify({type:'delta',text:'Un passaggio breve.'})+'\n\ndata: '+JSON.stringify({type:'done',view})+'\n\n'});
  });
  const composer=page.getByLabel('Messaggio al tutor');await composer.fill('Prima domanda.');await page.getByRole('button',{name:'Invia messaggio'}).click();
  await composer.fill('La prossima domanda, ancora in bozza.');await composer.focus();release();
  await expect(page.getByRole('button',{name:'Invia messaggio'})).toBeVisible();
  await expect(composer).toBeFocused();await expect(composer).toHaveValue('La prossima domanda, ancora in bozza.');
  await page.reload();await page.getByRole('button',{name:'Riprendi il percorso →'}).click();
  await expect(composer).toHaveValue('La prossima domanda, ancora in bozza.');
});


test('sessions can be searched and resumed and ChatGPT access is visible',async({page})=>{
  await page.goto('/');
  await page.getByRole('button',{name:'Sessioni',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Le tue sessioni'})).toBeVisible();
  await page.getByLabel('Cerca nelle sessioni').fill('');
  await page.getByRole('button',{name:'Cerca sessioni',exact:true}).click();
  await page.getByRole('button',{name:'Riprendi sessione',exact:true}).first().click();
  await expect(page.getByLabel('Messaggio al tutor')).toBeVisible();
  await page.getByRole('button',{name:'◇ Modello e accesso'}).click();
  await expect(page.getByRole('button',{name:'Collega ChatGPT',exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'◇ Modello e accesso'})).toBeFocused();
});

test('beginner mode starts from course sources and resumes its lesson phase after provider failure',async({page})=>{
  await page.goto('/');await page.getByRole('button',{name:'Parti dalle basi',exact:true}).click();
  const path=page.getByRole('region',{name:'Percorso dalle basi'});
  await expect(path).toBeVisible();await expect(page.getByRole('heading',{name:'Prima di iniziare'})).toHaveCount(0);
  await expect(page.getByRole('alert')).toContainText('Seleziona un modello disponibile');
  await expect(page.locator('.message.user')).toContainText('Parti da zero');
  await expect(path.getByLabel('Lezione',{exact:true})).toBeVisible();
  await page.reload();await page.getByRole('button',{name:'Riprendi il percorso →'}).click();
  await expect(path).toBeVisible();await expect(page.locator('.message.user')).toContainText('Parti da zero');
  await page.getByRole('button',{name:'Programma',exact:true}).click();
  await expect(page.getByRole('button',{name:'Studia questa lezione →'}).first()).toBeVisible();
});

test('math is one accessible object under the pointer, with persistent text and symbol alternatives',async({page})=>{
  await page.route('**/api/sessions',async route=>{
    const response=await route.fetch(),view=await response.json();
    view.messages.push({id:'accessible-formula',role:'assistant',text:'Il costo è $T(n)=an+b$. Verifica `i ≤ n`.\n\n```text\ni ≤ n\n```',created:'2099-01-01T00:00:00Z'});
    await route.fulfill({json:view});
  });
  await page.goto('/');await page.getByRole('button',{name:'Inizia una nuova sessione',exact:true}).click();
  const spoken=page.locator('.math-spoken-hitbox').filter({hasText:/T di n uguale a a per n più b/});
  const comparison=page.locator('.math-spoken-hitbox').filter({hasText:'i minore o uguale a n'});
  await expect(comparison).toHaveCount(1);await expect(comparison.locator('..').locator('code')).toHaveText('i ≤ n');
  await expect(page.locator('pre code')).toHaveText('i ≤ n\n');
  const formula=spoken.locator('..');
  await expect(formula).toBeVisible();await expect(formula.locator('.katex-html')).toBeVisible();
  const tree=await formula.ariaSnapshot();expect(tree.trim().split('\n').length).toBe(1);expect(tree).toContain('text:');
  const speechBox=await spoken.boundingBox(),formulaBox=await formula.boundingBox();expect(Math.abs(speechBox!.width-formulaBox!.width)).toBeLessThan(2);expect(Math.abs(speechBox!.height-formulaBox!.height)).toBeLessThan(2);
  await formula.scrollIntoViewIfNeeded();
  const glyph=formula.locator('.katex-html .mord').filter({hasText:/^n$/}).first();const box=await glyph.boundingBox();expect(box).not.toBeNull();
  const target=await page.evaluate(({x,y})=>document.elementFromPoint(x,y)?.classList.contains('math-spoken-hitbox'),{x:box!.x+box!.width/2,y:box!.y+box!.height/2});expect(target).toBe(true);
  await page.getByText('Accessibilità',{exact:true}).click();const mode=page.getByLabel('Modalità di lettura delle formule');
  await mode.selectOption('text');await expect(page.locator('.math-readable').filter({hasText:/T di n/})).toBeVisible();await expect(spoken).toHaveCount(0);
  await page.reload();await page.getByRole('button',{name:'Riprendi il percorso →'}).click();await expect(page.locator('.math-readable').filter({hasText:/T di n/})).toBeVisible();
  await page.getByText('Accessibilità',{exact:true}).click();await mode.selectOption('symbols');await expect(page.locator('.math-unit[role="math"]')).toHaveCount(0);await expect(page.locator('.katex-html').first()).toBeVisible();
});


test('short conversations keep the composer at the bottom and long ones keep it reachable',async({page})=>{
  await page.setViewportSize({width:1280,height:1000});
  await page.route('**/api/sessions',async route=>{
    const response=await route.fetch(),view=await response.json();
    view.activities=[];view.messages=[{id:'short-layout',role:'assistant',text:'Da quale concetto vuoi iniziare?',created:'2099-01-01T00:00:00Z'}];
    await route.fulfill({json:view});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'Inizia una nuova sessione',exact:true}).click();
  const composer=page.locator('.composer'),input=page.getByLabel('Messaggio al tutor');
  await expect(composer).toBeVisible();
  const box=await composer.boundingBox();
  expect(box!.y+box!.height).toBeGreaterThan(900);
  expect(box!.y+box!.height).toBeLessThanOrEqual(1000);
  await input.fill('La mia bozza');
  await input.focus();
  // Exercise content growth while preserving focus and the student's draft.
  await page.locator('.messages').evaluate(el=>{
    const paragraph=document.createElement('p');paragraph.textContent='Una spiegazione lunga. '.repeat(2000);el.appendChild(paragraph);
  });
  await expect(input).toBeFocused();await expect(input).toHaveValue('La mia bozza');
  await expect(composer).toBeInViewport();
  await page.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));
  await expect(composer).toBeInViewport();
  await page.setViewportSize({width:700,height:900});
  await page.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));
  await expect(input).toBeInViewport();
  await expect(input).toHaveValue('La mia bozza');
});

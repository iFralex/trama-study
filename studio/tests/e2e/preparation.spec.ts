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

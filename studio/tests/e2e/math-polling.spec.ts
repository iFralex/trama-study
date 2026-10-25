import {test,expect} from '@playwright/test';

test('readable formulas and following text stay stable across course polling',async({page})=>{
  const formula=String.raw`F=(a_0\land b_0)\lor(a_1\land b_1)\lor(a_2\land b_2)\lor(a_3\land b_3).`;
  const speech='F uguale a '+Array(4).fill('aperta parentesi a con indice zero e b con indice zero chiusa parentesi').join(' oppure ');
  const session={session:{id:'math-session',mode:'learn',minutes:25,goal:'Test',current:null},curriculum:{path:'math-path'},activities:[],messages:[],attempts:[],progress:[]};
  const path={id:'math-path',sid:'math-session',status:'ready',objective:{request:'Test'},coverage:[],plan:{version:1,data:{final:true}},chapters:[{id:'boolean',title:'Aggregazione booleana',ready:true,version:1}],position:{chapter:'boolean',block:'formula'},current:{chapter:'boolean',version:1,content:{blocks:[{id:'formula',kind:'text',text:'$$\n'+formula+'\n$$\n\nLe coppie di input occupano otto celle distinte.\n\n'+('Testo successivo.\n\n'.repeat(35)),sources:[]}]}},profile:{total:0,formats:{},questions:[]},recalls:[],journal:[],revisions:[],reservations:[]};
  let reads=0;
  await page.addInitScript(()=>{localStorage.setItem('studio-last-view','corso');localStorage.setItem('studio-math-reading','text');});
  await page.route('**/*',async route=>{
    if(new URL(route.request().url()).pathname.startsWith('/api/'))return route.fallback();
    await route.fulfill({response:await route.fetch()});
  });
  // All API traffic is isolated from the user's archive and model providers.
  await page.route('**/api/**',async route=>{
    const url=new URL(route.request().url()).pathname;
    let data:unknown={};
    if(url==='/api/bootstrap')data={selected:'math-course',courses:[{id:'math-course',label:'Test'}]};
    else if(url.endsWith('/inventory'))data={documents:[],proposed:[]};
    else if(url.endsWith('/paths'))data=[path];
    else if(url==='/api/paths/math-path'){reads++;data=path;}
    else if(url.endsWith('/open')||url==='/api/sessions/math-session')data=session;
    else if(url==='/api/math-speech')data={speech};
    await route.fulfill({json:data});
  });
  await page.goto('/');
  const panel=page.getByLabel('Contenuto del capitolo');
  await expect(panel.locator('.math-readable')).toHaveText(speech);
  const initial=await panel.evaluate(el=>{
    el.scrollTop=120;
    const formula=el.querySelector('.math-readable')!;
    const following=[...el.querySelectorAll('p')].find(p=>p.textContent?.startsWith('Le coppie'))!;
    let unstable=false;
    const height=el.scrollHeight,top=following.getBoundingClientRect().top,scroll=el.scrollTop;
    const observer=new MutationObserver(()=>{if(!formula.isConnected||el.scrollHeight!==height||following.getBoundingClientRect().top!==top)unstable=true;});
    observer.observe(el,{childList:true,subtree:true,characterData:true});
    (window as any).mathPollingProbe={result:()=>({unstable,connected:formula.isConnected,height:el.scrollHeight,top:following.getBoundingClientRect().top,scroll:el.scrollTop}),stop:()=>observer.disconnect()};
    return {height,top,scroll};
  });
  const started=reads;
  await expect.poll(()=>reads,{timeout:10000}).toBeGreaterThanOrEqual(started+3);
  const result=await page.evaluate(()=>{const probe=(window as any).mathPollingProbe;probe.stop();return probe.result();});
  expect(result).toEqual({...initial,unstable:false,connected:true});
});

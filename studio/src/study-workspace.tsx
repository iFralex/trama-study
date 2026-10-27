import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {timeRange,useStudyClock,StudyTimeOverview} from './study-time';

type Props={studyTime:any,path:any,view:any,busy:boolean,working:boolean,chat:(quote:string)=>React.ReactNode,source:React.ReactNode,sourceId?:string,history:React.ReactNode,onSelect:(chapter:any)=>Promise<void>,onMark:(block:string)=>Promise<void>,onAsk:(text:string)=>Promise<void>,onSource:(id:string)=>void,onExitRecall:()=>Promise<void>,onReturn:()=>Promise<void>,onTraining:()=>void,renderProse:(text:string)=>React.ReactNode,renderActivity:(id:string,version?:number)=>React.ReactNode,updateAvailable:boolean,onUpdate:()=>Promise<void>,tutorRequest:number};

export function StudyWorkspace(props:Props){
  const {path,view,busy,working,onSelect,onMark,onAsk,onSource,renderProse,renderActivity}=props;
  const [index,setIndex]=useState(false),[pinned,setPinned]=useState(()=>localStorage.getItem('studio-index-pinned')==='true');
  const [small,setSmall]=useState(()=>matchMedia('(max-width: 900px)').matches),[narrow,setNarrow]=useState(()=>matchMedia('(max-width: 1200px)').matches);
  const [side,setSide]=useState(''),[quote,setQuote]=useState(''),[resume,setResume]=useState(()=>sessionStorage.getItem('studio-resume-dismissed:'+path.id)!=='true');
  const [width,setWidth]=useState(()=>Math.max(300,Math.min(560,Number(localStorage.getItem('studio-panel-width'))||380)));
  const indexVisible=index||(pinned&&!small&&(!side||!narrow));
  const [query,setQuery]=useState(''),[results,setResults]=useState<any[]>([]),[searchError,setSearchError]=useState(''),[searching,setSearching]=useState(false);
  const reader=useRef<HTMLDivElement>(null),indexButton=useRef<HTMLButtonElement>(null),sideButton=useRef<HTMLButtonElement>(null);
  const timer=useRef<ReturnType<typeof setTimeout>|null>(null),latest=useRef(props);latest.current=props;
  const chapter=path.chapters.find((c:any)=>c.id===path.current?.chapter),chapterIndex=path.chapters.findIndex((c:any)=>c.id===chapter?.id);
  const blocks=path.current?.content.blocks??[],blockIndex=Math.max(0,blocks.findIndex((b:any)=>b.id===path.position?.block));
  const scrollKey=path.current?'studio-course-scroll:'+path.id+':'+path.current.chapter+':'+path.current.version:'';
  const matches=view?.session.id===path.sid&&view?.curriculum?.path===path.id;
  const estimate=props.studyTime.estimate,chapterTime=estimate?.chapters?.find((c:any)=>c.id===path.current?.chapter);
  const clock=useStudyClock(path.current&&blocks[blockIndex]?{sid:path.sid,path:path.id,chapter:path.current.chapter,version:path.current.version,block:blocks[blockIndex].id}:null,!!estimate?.tracking&&matches&&!busy&&!working&&!side&&!path.recall&&!path.objective.archived,props.studyTime.refresh);
  async function studyMark(block:string,status:string){const target={path:path.id,sid:path.sid,chapter:path.current.chapter,version:path.current.version};await clock.flush();await props.studyTime.mark(block,status,target);}

  useLayoutEffect(()=>{if(reader.current&&scrollKey)reader.current.scrollTop=Number(localStorage.getItem(scrollKey)??0);},[scrollKey,path.recall?.activity]);
  useEffect(()=>()=>{if(timer.current)clearTimeout(timer.current);},[scrollKey,path.sid]);
  useEffect(()=>{setQuote('');setIndex(false);setResume(sessionStorage.getItem('studio-resume-dismissed:'+path.id)!=='true');setResults([]);setQuery('');},[path.id]);
  useEffect(()=>{if(props.sourceId&&!path.recall)setSide('sources');},[props.sourceId]);
  useEffect(()=>{if(props.tutorRequest&&!path.recall)setSide('tutor');},[props.tutorRequest]);
  useEffect(()=>{if(path.recall){setSide('');setIndex(false);setQuote('');}},[path.recall]);
  useEffect(()=>{const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'){if(side){setSide('');setTimeout(()=>sideButton.current?.focus(),0);}else if(index){setIndex(false);indexButton.current?.focus();}setQuote('');}};document.addEventListener('keydown',escape);return()=>document.removeEventListener('keydown',escape);},[side,index]);
  useEffect(()=>{const media=matchMedia('(max-width: 900px)'),compact=matchMedia('(max-width: 1200px)');const update=()=>{setSmall(media.matches);setNarrow(compact.matches);};media.addEventListener('change',update);compact.addEventListener('change',update);return()=>{media.removeEventListener('change',update);compact.removeEventListener('change',update);};},[]);
  useEffect(()=>{if(side&&small)document.querySelector<HTMLButtonElement>('.study-companion .companion-close')?.focus();},[side,small]);

  useEffect(()=>{
    if(!side||!small)return;
    const background=[...document.querySelectorAll<HTMLElement>('.rail,.topbar,.course-toolbar,.course-status,.resume-card,.reading-toolbar,.reader-column,.reading-index')];
    const previous=background.map(el=>el.inert);background.forEach(el=>{el.inert=true;});
    const trap=(event:KeyboardEvent)=>{
      if(event.key!=='Tab')return;
      const items=[...document.querySelectorAll<HTMLElement>('.study-companion button:not(:disabled),.study-companion input:not(:disabled),.study-companion textarea:not(:disabled),.study-companion select:not(:disabled),.study-companion summary,.study-companion a[href]')].filter(el=>el.tabIndex!==-1&&el.getClientRects().length>0);
      const first=items[0],last=items.at(-1);if(!first)return;
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    };
    document.addEventListener('keydown',trap);
    return()=>{background.forEach((el,i)=>{el.inert=previous[i];});document.removeEventListener('keydown',trap);};
  },[side,small]);

  function savePosition(){
    const el=reader.current;if(!el)return;
    if(scrollKey)localStorage.setItem(scrollKey,String(el.scrollTop));
    if(timer.current)clearTimeout(timer.current);
    timer.current=setTimeout(()=>{
      const current=latest.current;if(current.path.recall||!reader.current)return;
      const top=reader.current.getBoundingClientRect().top;
      const block=[...reader.current.querySelectorAll<HTMLElement>('[data-course-block]')].find(b=>b.getBoundingClientRect().bottom>top+65);
      if(block?.dataset.courseBlock&&block.dataset.courseBlock!==current.path.position?.block)void current.onMark(block.dataset.courseBlock);
    },400);
  }
  async function goBlock(index:number){
    const block=blocks[index];if(!block)return;
    if(timer.current){clearTimeout(timer.current);timer.current=null;}
    await onMark(block.id);
    reader.current?.querySelector<HTMLElement>('[data-course-block="'+CSS.escape(block.id)+'"]')?.scrollIntoView({block:'start',behavior:'instant'});
  }
  function selection(){
    const selected=window.getSelection();
    if(!selected||selected.isCollapsed||!reader.current?.contains(selected.anchorNode)||!reader.current.contains(selected.focusNode)){setQuote('');return;}
    setQuote(selected.toString().trim().slice(0,5000));
  }
  async function ask(action:string){
    if(!quote||busy||path.recall)return;
    setSide('tutor');
    await onAsk(action+' sul passaggio del capitolo «'+chapter?.title+'»:\n\n> '+quote.replaceAll('\n','\n> '));
  }
  async function search(e:React.FormEvent){
    e.preventDefault();if(!query.trim()||!path.sid)return;setSearching(true);setSearchError('');
    try{const response=await fetch('/api/sessions/'+path.sid+'/search?q='+encodeURIComponent(query));const data=await response.json();if(!response.ok)throw Error(data.error);setResults(data);}catch(e:any){setSearchError(e.message);}finally{setSearching(false);}
  }
  const sources=[...new Set<string>(blocks.flatMap((b:any)=>b.sources??view?.activities?.find((a:any)=>a.id===b.activity&&a.version===b.activity_version)?.spec.sources??[]))];
  function changeWidth(value:number){const next=Math.round(Math.max(300,Math.min(560,window.innerWidth-530,value)));setWidth(next);localStorage.setItem('studio-panel-width',String(next));}
  const indexContent=<><header><h2>Nel tuo percorso</h2><button onClick={()=>{setIndex(false);indexButton.current?.focus();}} aria-label="Chiudi indice">×</button></header><label className="course-check"><input type="checkbox" checked={pinned} onChange={e=>{setPinned(e.target.checked);setIndex(false);localStorage.setItem('studio-index-pinned',String(e.target.checked));}}/>Mantieni aperto su desktop</label><nav aria-label="Capitoli del corso">{path.chapters.map((c:any,i:number)=><div className="chapter-entry" key={c.id}><button aria-current={chapter?.id===c.id?'step':undefined} disabled={working||busy} onClick={()=>void onSelect(c).then(()=>{setIndex(false);setResume(false);})}><small>CAPITOLO {i+1}</small><strong>{c.title}</strong><span>{c.ready?(c.stale?'Fonti da aggiornare':'Disponibile'):'Da preparare'}</span></button><small>{timeRange(estimate?.chapters?.find((t:any)=>t.id===c.id)?.total)} · {c.ready?'sui contenuti':'dal programma'}</small>{c.progress&&<small>{c.progress.status}{c.progress.provisional?' · provvisorio':''}</small>}</div>)}</nav></>;

  return <div className="study-space">
    {resume&&chapter&&!path.recall&&<section className="resume-card" aria-label="Riprendi lo studio"><div><span className="eyebrow">IL TUO PUNTO DI PARTENZA</span><h2>{chapter.title}</h2><p>Capitolo {chapterIndex+1} di {path.chapters.length} · punto {blockIndex+1} di {blocks.length}{blocks[blockIndex]?.activity?' · '+(view?.activities?.find((a:any)=>a.id===blocks[blockIndex].activity)?.spec.title??'Esercizio'):''}</p>{path.recalls.length>0&&<button className="resume-recalls" onClick={props.onTraining}>{path.recalls.length} richiami programmati · Apri allenamento</button>}</div><button className="primary" onClick={()=>{setResume(false);sessionStorage.setItem('studio-resume-dismissed:'+path.id,'true');reader.current?.focus({preventScroll:true});}}>Continua a studiare →</button></section>}
    <div className="reading-toolbar"><div className="reading-tools"><button ref={indexButton} disabled={!!path.recall} aria-expanded={indexVisible} aria-controls="study-index" onClick={()=>{if(indexVisible&&pinned&&!small){setPinned(false);setIndex(false);localStorage.setItem('studio-index-pinned','false');}else setIndex(v=>!v);}}>☰ Indice</button><span className="quiet">{path.recall?'Richiamo senza aiuti':chapter?'Capitolo '+(chapterIndex+1)+' / '+path.chapters.length:'Il tuo percorso'}</span></div><div className="reading-tools">{props.updateAvailable&&<button disabled={working||busy} onClick={()=>void props.onUpdate()}>Aggiornamento disponibile · Applica</button>}{[['tutor','Tutor'],['sources','Fonti']].map(([id,label])=><button key={id} ref={id==='tutor'?sideButton:undefined} disabled={!!path.recall} aria-expanded={side===id} aria-controls="study-companion" onClick={()=>setSide(v=>v===id?'':id)}>{label}</button>)}</div></div>
    {!path.recall&&<div className="study-time-toolbar" aria-label="Tempo di studio del capitolo"><div><strong>{timeRange(chapterTime?.total)}</strong><span className="quiet"> · rimanente {timeRange(chapterTime?.remaining)}</span><details><summary>Tempi e ritmo</summary><StudyTimeOverview data={estimate} onSettings={props.studyTime.settings} working={props.studyTime.working}/>{chapterTime&&<p>Lettura ed esempi: {timeRange(chapterTime.breakdown.reading)} · Esercizi: {timeRange(chapterTime.breakdown.practice)} · Riscontro: {timeRange(chapterTime.breakdown.review)}.</p>}</details></div><div className="study-clock"><span className="quiet">{clock.state}</span><button disabled={!estimate?.tracking} onClick={()=>void clock.toggle()}>{clock.paused?'Riprendi tempo':'Pausa tempo'}</button></div>{(props.studyTime.error||clock.error)&&<p role="alert">{props.studyTime.error||clock.error}</p>}</div>}
    <div className={'reading-workspace'+(pinned?' index-pinned':'')+(side?' companion-open':'')} style={{'--companion-width':width+'px'} as React.CSSProperties}>
      <aside id="study-index" className={'reading-index'+(index?' index-open':'')} hidden={!indexVisible}>{indexContent}</aside>
      <div className="reader-column">
        <div className="course-content" ref={reader} role="region" tabIndex={0} aria-label="Contenuto del capitolo" onScroll={savePosition} onMouseUp={selection} onKeyUp={e=>{if(e.key==='Shift'||e.key.startsWith('Arrow'))selection();}}>
          {path.recall?<><h1>Richiamo senza aiuti</h1><p>Concentrati sul ragionamento. Capitolo, tutor e fonti tornano disponibili alla consegna o quando esci.</p>{renderActivity(path.recall.activity)}<button onClick={()=>void props.onExitRecall()}>Torna al capitolo</button></>:path.current?<>
            <header className="chapter-heading"><span className="eyebrow">CAPITOLO {chapterIndex+1}</span><h1>{chapter?.title}</h1>{chapter?.objective&&<p className="chapter-objective">{chapter.objective}</p>}<details className="chapter-provenance"><summary>Fonti e revisione del capitolo</summary><p>Versione {path.current.version} · {path.current.content.review?'Revisioni AI completate; giudizio provvisorio.':'Contenuto storico.'} Leggere e avanzare non certifica la comprensione.</p>{path.current.stale&&<p>Le fonti sono cambiate: è disponibile una verifica del percorso.</p>}</details></header>
            {blocks.map((b:any,index:number)=><section className="course-block" data-course-block={b.id} key={b.id} aria-label={'Sezione '+(index+1)}><div className="block-heading"><span>{String(index+1).padStart(2,'0')} · {b.kind==='text'?'LEGGI E COMPRENDI':'METTITI ALLA PROVA'}</span><button className="course-position" aria-pressed={path.position?.block===b.id} onClick={()=>void onMark(b.id)}>{path.position?.block===b.id?'Punto attuale':'Riprendi da qui'}</button></div>{b.kind==='text'?<>{renderProse(b.text)}{b.sources?.length>0&&<div className="source-row"><span>Verifica sulle fonti</span>{b.sources.map((s:string,i:number)=><button key={s} onClick={()=>onSource(s)}>Fonte {i+1} ↗</button>)}</div>}</>:matches&&b.activity?renderActivity(b.activity,b.activity_version):<p>Carico l’attività salvata…</p>}<div className="study-block-progress" aria-label={'Studio della sezione '+(index+1)}><span className="quiet">{estimate?.current_blocks?.find((t:any)=>t.id===b.id)?.submitted?'Tentativo consegnato · ':''}{timeRange(estimate?.current_blocks?.find((t:any)=>t.id===b.id)?.remaining)} rimanenti</span>{[['studied','Studiato'],['review','Da rivedere'],['todo','Da studiare']].map(([value,label])=><button key={value} data-study-state={value} disabled={!estimate||props.studyTime.working} aria-pressed={estimate?.current_blocks?.find((t:any)=>t.id===b.id)?.status===value} onClick={()=>void studyMark(b.id,value)}>{label}</button>)}</div></section>)}
            {matches&&view.activities.filter((a:any)=>a.spec.curriculum?.extra&&a.spec.curriculum.chapter===path.current.chapter).map((a:any)=><React.Fragment key={a.id+':'+a.version}>{renderActivity(a.id,a.version)}</React.Fragment>)}
            {path.position?.return_state&&<button onClick={()=>void props.onReturn()}>Torna al punto precedente</button>}
          </>:<div className="reader-empty"><span className="eyebrow">IL TUO PERCORSO È IN PREPARAZIONE</span><h1>Presto, il primo capitolo.</h1><p>Puoi controllare il piano nell’indice. I contenuti compaiono dopo le revisioni.</p></div>}
        </div>
        {quote&&!path.recall&&<div className="selection-tools" aria-label="Chiedi sul testo selezionato"><span>{quote.length>80?quote.slice(0,80)+'…':quote}</span><button disabled={busy} onMouseDown={e=>e.preventDefault()} onClick={()=>void ask('Spiegami questo')}>Spiegami questo</button><button disabled={busy} onMouseDown={e=>e.preventDefault()} onClick={()=>void ask('Fammi un esempio concreto')}>Fammi un esempio</button><button aria-label="Deseleziona passaggio" onClick={()=>setQuote('')}>×</button></div>}
        {path.current&&!path.recall&&<footer className="reading-footer"><button disabled={blockIndex===0||working} onClick={()=>void goBlock(blockIndex-1)}>← Punto precedente</button><span className="quiet">{blockIndex+1} / {blocks.length}</span><button className="primary" disabled={working||busy||(blockIndex===blocks.length-1&&chapterIndex===path.chapters.length-1)} onClick={()=>{if(blockIndex<blocks.length-1)void goBlock(blockIndex+1);else if(path.chapters[chapterIndex+1])void onSelect(path.chapters[chapterIndex+1]);}}>{blockIndex<blocks.length-1?'Continua':'Capitolo successivo'} →</button></footer>}
      </div>
      <aside id="study-companion" className="study-companion" role={small&&side?'dialog':'complementary'} aria-modal={small&&side?true:undefined} hidden={!side||!!path.recall} aria-label="Strumenti di studio">
        <div className="panel-resizer" role="separator" aria-label="Larghezza pannello" aria-orientation="vertical" aria-valuenow={width} aria-valuemin={300} aria-valuemax={560} tabIndex={0} onKeyDown={e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();changeWidth(width+(e.key==='ArrowLeft'?20:-20));}}} onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);}} onPointerMove={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))changeWidth(e.currentTarget.parentElement!.getBoundingClientRect().right-e.clientX);}} onPointerUp={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}}/>
        <header className="companion-header"><div role="tablist" aria-label="Pannello di studio">{[['tutor','Tutor'],['sources','Fonti'],['history','Cronologia']].map(([id,label])=><button key={id} role="tab" id={'companion-tab-'+id} aria-selected={side===id} aria-controls={'companion-'+id} tabIndex={side===id?0:-1} onKeyDown={e=>{const tabs=['tutor','sources','history'];const direction=e.key==='ArrowRight'?1:e.key==='ArrowLeft'?-1:0;if(direction){e.preventDefault();const next=tabs[(tabs.indexOf(side)+direction+3)%3];setSide(next);document.getElementById('companion-tab-'+next)?.focus();}}} onClick={()=>setSide(id)}>{label}</button>)}</div><button className="companion-close" aria-label="Torna al capitolo" onClick={()=>{setSide('');setTimeout(()=>sideButton.current?.focus(),0);}}>×</button></header>
        <div id="companion-tutor" role="tabpanel" aria-labelledby="companion-tab-tutor" className="companion-body" hidden={side!=='tutor'}>{quote&&<blockquote className="discussion-context"><span className="eyebrow">PASSAGGIO SELEZIONATO</span>{quote}<button onClick={()=>setQuote('')} aria-label="Rimuovi riferimento">×</button></blockquote>}{props.chat(quote)}</div>
        <div id="companion-sources" role="tabpanel" aria-labelledby="companion-tab-sources" className="companion-body" hidden={side!=='sources'}>{props.source??<><h2>Le fonti del capitolo</h2><p className="quiet">Apri i riferimenti accanto al testo oppure cerca nei materiali del corso.</p><form className="search" onSubmit={e=>void search(e)}><label className="sr-only" htmlFor="chapter-source-search">Cerca nei materiali</label><input id="chapter-source-search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Cerca nei materiali…"/><button disabled={searching||!query.trim()}>Cerca</button></form>{searchError&&<p role="alert">{searchError}</p>}{results.map(r=><button className="search-result" key={r.id} onClick={()=>onSource(r.id)}>{r.title}{r.page!=null?' · pagina/cella '+r.page:''}<p>{r.text.slice(0,180)}…</p></button>)}{!query&&sources.map((id,i)=><button className="chapter-source" key={id} onClick={()=>onSource(id)}>Riferimento {i+1} ↗</button>)}</>}</div>
        <div id="companion-history" role="tabpanel" aria-labelledby="companion-tab-history" className="companion-body" hidden={side!=='history'}>{side==='history'&&props.history}</div>
      </aside>
    </div>
  </div>;
}

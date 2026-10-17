import React,{useMemo,useState} from 'react';
const phases:Record<string,string>={scope:'Definizione dell’esame',selection:'Selezione delle fonti',exam_reading:'Analisi degli esami autentici',evidence_reading:'Lettura delle fonti selezionate',map:'Mappa completa e prerequisiti',map_review:'Revisione della mappa',chapter:'Scrittura del capitolo',repair_chapter:'Correzione del capitolo',review_solve:'Risoluzione indipendente degli esercizi',review_discipline:'Revisione disciplinare completa',review_didactic:'Revisione didattica completa',publish:'Pubblicazione del capitolo revisionato'};
const states:Record<string,string>={relevant:'Pertinente',prerequisite:'Prerequisito',outside:'Fuori perimetro',uncertain:'Da verificare',unreviewed:'Da selezionare'};
export function PreparationPanel({path,onDecision,onIssue,onSource,working}:{path:any,onDecision:(source:string,status:string,reason:string)=>Promise<void>,onIssue:(id:string,note:string)=>Promise<void>,onSource:(id:string)=>void,working:boolean}){
  const [notes,setNotes]=useState<Record<string,string>>({}),[limits,setLimits]=useState<Record<string,number>>({});
  const groups=useMemo(()=>{
    const map=new Map<string,{title:string,documents:any[]}>();
    for(const doc of path.coverage){
      const lesson=doc.path.match(/\/(\d{4}-\d{2}-\d{2}_[^/]+)\/(?:trascrizione|allineamento)\//)?.[1];
      const key=lesson??doc.id,title=lesson?(doc.lesson_label??lesson.slice(0,10)+' · Lezione'):doc.title;
      if(!map.has(key))map.set(key,{title,documents:[]});map.get(key)!.documents.push(doc);
    }
    return [...map.entries()];
  },[path.coverage]);
  const progress=path.preparation,decisions=path.decisions??[];
  const selected=decisions.filter((d:any)=>d.status!=='outside'),done=selected.filter((d:any)=>d.done).length;
  return <>
    <section className="preparation-progress" aria-label="Preparazione dalle fonti originali">
      <div><span className="eyebrow">PREPARAZIONE · FONTI ORIGINALI</span><h2>{phases[progress?.phase]??'Ricognizione del corso'}</h2></div>
      <p>{done} intervalli analizzati · {selected.length} inclusi o da verificare · {decisions.length-selected.length} fuori perimetro.</p>
      <p className="quiet">{progress?.current_task?.state==='correcting'?'Correggo il risultato rifiutato, senza alterare i checkpoint.':path.status==='running'?'Il modello sta lavorando. I risultati compaiono al salvataggio del checkpoint.':path.status==='error'?'Preparazione interrotta: i checkpoint completati sono conservati.':path.status==='confirm'||path.status==='clarification'?'Rivedi la scheda dell’esame prima della lettura approfondita.':path.status==='ready'?'I capitoli vicini sono revisionati: puoi studiare o scegliere un altro capitolo.':'Puoi riprendere dal primo compito mancante.'}</p>
      {progress?.last_checkpoint&&<p className="quiet">Ultimo checkpoint: {new Date(progress.last_checkpoint).toLocaleString('it-IT')}.</p>}
      <p className="quiet">Materiale analizzato, contenuto revisionato e capacità dimostrata sono indicatori distinti.</p>
    </section>
    <details className="course-audit"><summary>Fonti selezionate, lezioni ed esclusioni</summary>
      <p>La selezione è automatica e modificabile. «Da verificare» richiede approfondimento; una data o un nome di file non dimostrano il perimetro.</p>
      {groups.map(([key,group])=><details className="preparation-source-group" key={key}><summary>{group.title} · {group.documents.length} {group.documents.length===1?'fonte':'fonti'}</summary>{group.documents.map(doc=>{
        const spans=decisions.filter((d:any)=>d.document===doc.id),limit=limits[doc.id]??20;
        return <article key={doc.id}><h3>{doc.display_title??doc.title}</h3><p className="quiet">{doc.structural?'Collegamenti strutturati fra video, slide e notebook; non vengono riassunti come testo.':doc.reserved?'Prova riservata: esclusa dal modello.':doc.solution?'Soluzione separata dal programma didattico.':doc.excluded?'Fonte esclusa: '+(doc.issue??(doc.administrative?'amministrativa':doc.duplicate_of?'copia identica':'non utilizzabile')):doc.done+' intervalli analizzati.'}</p>
          {spans.slice(0,limit).map((span:any)=><div className="preparation-decision" key={span.source}><button onClick={()=>onSource(span.source)}>{span.page!=null?'Pagina/cella '+span.page:span.start!=null?Math.floor(span.start/60)+':'+String(Math.floor(span.start%60)).padStart(2,'0')+' → '+Math.floor(span.end/60)+':'+String(Math.floor(span.end%60)).padStart(2,'0'):'Apri fonte'} ↗</button><label><span className="sr-only">Selezione per {span.source}</span><select disabled={working} value={span.status} onChange={e=>void onDecision(span.source,e.target.value,'Selezione modificata dallo studente')}>{Object.entries(states).map(([value,label])=><option key={value} value={value} disabled={value==='unreviewed'}>{label}</option>)}</select></label><p>{span.reason}</p><small>{span.done?'Analizzato':'Non ancora analizzato'}</small></div>)}
          {spans.length>limit&&<button onClick={()=>setLimits(old=>({...old,[doc.id]:limit+30}))}>Mostra altri intervalli ({spans.length-limit})</button>}
        </article>;
      })}</details>)}
    </details>
    {progress?.issues?.length>0&&<details className="course-audit" open><summary>Problemi aperti e chiarimenti</summary>{progress.issues.map((issue:any)=><article className="course-note" key={issue.id}><strong>{issue.severity==='blocking'?'Punto sospeso':'Nota di revisione'} · {issue.chapter}</strong><p>{issue.data.message}</p>{issue.data.question&&<p>{issue.data.question}</p>}<p className="quiet">Le altre parti del capitolo restano disponibili. Un chiarimento viene sottoposto a nuova revisione.</p>{issue.data.student_note&&<p>Il tuo chiarimento: {issue.data.student_note}</p>}<label>Chiarimento per il tutor<textarea value={notes[issue.id]??''} onChange={e=>setNotes(old=>({...old,[issue.id]:e.target.value}))}/></label><button disabled={working||!notes[issue.id]?.trim()} onClick={()=>void onIssue(issue.id,notes[issue.id])}>Salva e richiedi revisione</button></article>)}</details>}
  </>;
}

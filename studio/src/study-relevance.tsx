import React from 'react';

const labels:Record<string,string>={exam:'Esame',foundation:'Fondamento',support:'Complementare',uncertain:'Da verificare'};

export function StudyRelevance({focus,onSource}:{focus:any,onSource:(id:string)=>void}){
  if(!focus||!labels[focus.role])return null;
  return <details className="study-relevance" data-relevance={focus.role}>
    <summary aria-label={'Rilevanza: '+labels[focus.role]}>{labels[focus.role]}</summary>
    <p>{focus.reason}</p>
    {!!focus.references?.length&&<ul>{focus.references.map((ref:any)=><li key={ref.question}><button className="source-link" onClick={()=>onSource(ref.sources[0])}>{ref.label} ↗</button></li>)}</ul>}
    <p className="quiet">{focus.role==='foundation'?'Prerequisito necessario per affrontare i quesiti indicati.':focus.role==='exam'?'Riscontro in temi precedenti; non indica una probabilità di uscita.':focus.role==='support'?'Contenuto del corso spiegato senza esercizi assegnati.':'Riscontro insufficiente nel campione consultato; non significa esclusione dal programma.'}</p>
  </details>;
}

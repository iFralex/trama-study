import React from 'react';

export type ReviewProgress={status:'pending'|'done'|'error',text?:string,error?:string};

export function AttemptFeedback({attempt,review,busy,onAssess,onOpenTutor,renderProse,children}:{attempt:any,review?:ReviewProgress,busy:boolean,onAssess:()=>void,onOpenTutor:()=>void,renderProse:(text:string)=>React.ReactNode,children:React.ReactNode}){
  const grade=attempt.grade,pending=review?.status==='pending',failed=review?.status==='error';
  const ungraded=grade.correct==null&&!grade.previous&&grade.status!=='verified';
  const text=review?.text?.trim(),assessed=!!grade.previous||grade.status==='verified';
  const ready=assessed||review?.status==='done'&&!!text;
  const title=pending?'CORREZIONE IN CORSO':failed&&!assessed?'CORREZIONE NON COMPLETATA':grade.status==='verified'?'VERIFICA AUTOMATICA':grade.previous?'VALUTAZIONE DEL TUTOR · PROVVISORIA':ungraded?(text?'RISCONTRO DEL TUTOR':'RISPOSTA SALVATA'):'VALUTAZIONE PROVVISORIA';
  return <div aria-label="Riscontro sulla risposta" className={'feedback '+(!pending&&grade.correct===true?'correct':'')} aria-busy={pending}>
    <div role="status"><span className="eyebrow">{title}</span>{pending&&<p>Risposta salvata. Il tutor sta analizzando il ragionamento e confrontandolo con le fonti. Il riscontro comparirà qui automaticamente.</p>}{failed&&<p>{assessed?'La valutazione è salvata, ma la spiegazione del tutor non è stata completata.':'La risposta è salvata. La richiesta al tutor non è stata completata.'}{review.error?' '+review.error:''}</p>}</div>
    {pending?text&&<div className="review-stream">{renderProse(text)}</div>:<>
      {(!ungraded&&(!failed||assessed))?renderProse(grade.feedback):text?renderProse(text):!failed&&<p>La risposta è salvata. La correzione del tutor non è ancora disponibile.</p>}
      {text&&!ungraded&&<details><summary>Spiegazione del tutor</summary>{renderProse(text)}</details>}
      {ready&&!failed&&<p className="feedback-next">Prossimo passo: {grade.correct===true?'prova a spiegare perché il procedimento funziona, poi continua.':grade.correct===false?'rivedi il ragionamento usando il riscontro e prova di nuovo.':'leggi il riscontro e chiedi un chiarimento sui punti ancora aperti.'}</p>}
      {failed||!ready&&grade.status!=='verified'?<button onClick={onAssess} disabled={busy}>{failed?'Riprova la correzione':'Chiedi la correzione al tutor'}</button>:grade.status!=='verified'&&<button onClick={onOpenTutor}>Apri il tutor per un chiarimento</button>}
    </>}
    {!!attempt.aids&&<p className="quiet">Tentativo con {attempt.aids} aiuti.</p>}
    {!pending&&children}
  </div>;
}

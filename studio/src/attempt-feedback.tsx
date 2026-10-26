import React from 'react';

export type ReviewProgress={status:'pending'|'done'|'error',text?:string,error?:string};
export function friendlyReviewError(message:string){
  if(/stream ended before a terminal response event|stream ended before message_stop|socket hang up|connection.*(?:closed|lost)/i.test(message))return 'La connessione con il modello si è interrotta prima della conclusione della spiegazione.';
  return message;
}

export function AttemptFeedback({attempt,review,busy,onAssess,onOpenTutor,onResumeExplanation,renderProse,children}:{attempt:any,review?:ReviewProgress,busy:boolean,onAssess:()=>void,onOpenTutor:()=>void,onResumeExplanation:()=>void,renderProse:(text:string)=>React.ReactNode,children:React.ReactNode}){
  const grade=attempt.grade,pending=review?.status==='pending',failed=review?.status==='error';
  const text=review?.text?.trim(),assessed=!!grade.previous||grade.status==='verified';
  const title=pending?(assessed?'SPIEGAZIONE IN CORSO':'CORREZIONE IN CORSO'):failed&&!assessed?'CORREZIONE NON COMPLETATA':grade.status==='verified'?'VERIFICA AUTOMATICA':grade.previous?'VALUTAZIONE DEL TUTOR · PROVVISORIA':'RISPOSTA SALVATA';
  function explain(){onOpenTutor();onResumeExplanation();}
  return <div aria-label="Riscontro sulla risposta" className={'feedback '+(!pending&&assessed&&grade.correct===true?'correct':'')} aria-busy={pending}>
    <div role="status"><span className="eyebrow">{title}</span>{pending&&<p>{assessed?'La valutazione è già salvata. Il tutor sta completando la spiegazione nella chat.':'Risposta salvata. Il tutor sta analizzando il ragionamento e confrontandolo con le fonti. Il riscontro comparirà qui automaticamente.'}</p>}{failed&&<p>{assessed?'La valutazione qui sotto è completa e salvata. Si è interrotta soltanto la spiegazione aggiuntiva.':'La risposta è salvata. La richiesta al tutor non è stata completata.'}{review.error?' '+friendlyReviewError(review.error):''}</p>}</div>
    {failed&&review.error&&friendlyReviewError(review.error)!==review.error&&<details><summary>Dettagli tecnici</summary><p>{review.error}</p></details>}
    {assessed&&renderProse(grade.feedback)}
    {!pending&&<>
      {!assessed&&!failed&&<p>{text?'Il tutor ha risposto nella chat, ma la valutazione del tentativo non è stata registrata.':'La risposta è salvata. La correzione del tutor non è ancora disponibile.'}</p>}
      {assessed&&<p className="feedback-next">Prossimo passo: {grade.correct===true?'prova a spiegare perché il procedimento funziona, poi continua.':grade.correct===false?'rivedi il ragionamento usando il riscontro e prova di nuovo.':'leggi il riscontro e chiedi un chiarimento sui punti ancora aperti.'}</p>}
      {text&&<p className="quiet">{assessed?'La spiegazione estesa è nella chat del tutor.':'La risposta estesa del tutor è disponibile nella chat.'}</p>}
      <div className="action-row">
        {failed&&assessed?<button onClick={explain} disabled={busy}>Riprendi la spiegazione</button>:!assessed?<button onClick={onAssess} disabled={busy}>{failed?'Riprova la correzione':'Chiedi la correzione al tutor'}</button>:grade.status!=='verified'&&!text&&<button onClick={explain} disabled={busy}>Spiega la valutazione</button>}
        {(text||assessed)&&<button onClick={onOpenTutor}>Apri il tutor per un chiarimento</button>}
      </div>
      {children}
    </>}
    {!!attempt.aids&&<p className="quiet">Tentativo con {attempt.aids} aiuti.</p>}
  </div>;
}

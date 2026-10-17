/** Versioned routing rules. Expensive reasoning is reserved for decisions and checks. */
export type ModelRef={provider:string,id:string};
export type Routing={version:string,provider:string,worker:string,expert:string};
export const HYBRID_ROUTING={enabled:true,version:'hybrid-2',provider:'openai',worker:'gpt-6-luna',expert:'gpt-6.1-sol'};
export function routingConfig(value:any,selected?:ModelRef):Routing|null{
  if(value?.enabled!==true||!selected||selected.provider!==value.provider)return null;
  if(![value.provider,value.worker,value.expert].every(x=>typeof x==='string'&&x.length>0&&x.length<100))throw Error('Configurazione dei modelli di preparazione non valida.');
  return {version:'hybrid-2',provider:value.provider,worker:value.worker,expert:value.expert};
}
export function preparationRoute(task:any,policy:Routing|null,selected:ModelRef):{model:ModelRef,worker:boolean,reason:string}{
  if(!policy)return {model:selected,worker:false,reason:'Modello selezionato: assegnazione automatica disattivata.'};
  const expert=(reason:string)=>({model:{provider:policy.provider,id:policy.expert},worker:false,reason});
  if(task.kind!=='selection')return expert('Analisi disciplinare, decisione, produzione didattica o verifica completa: Sol.');
  if(task.selection_history?.reviewed>=8&&task.selection_history.outside===task.selection_history.reviewed)return expert('Gli intervalli già verificati di questo documento sono tutti esclusi: evito il probabile doppio passaggio.');
  const inputs=[...(task.sources??[]),...(task.previews??[]),...(task.links??[]).map((l:any)=>l.source)];
  if(inputs.some((s:any)=>s.kind==='notebook'||/parziale|incomplet|\blow\b|bassa|\bOCR\b|ambig/i.test(String(s.quality))))return expert('Codice strutturato o fonte incompleta/ambigua da interpretare.');
  if((task.links??[]).some((l:any)=>/low|bassa/i.test(String(l.confidence))))return expert('Associazione fra lezione e materiale a bassa affidabilità.');
  return {model:{provider:policy.provider,id:policy.worker},worker:true,reason:'Selezione circoscritta: Luna; Sol verifica soltanto le esclusioni, senza rifare l’intero compito.'};
}
export function expertCheckReason(kind:string,result:any):string|null{
  if(result?.needs_expert===true||(Array.isArray(result?.expert_questions)&&result.expert_questions.length))return 'Il lettore segnala un dubbio che richiede verifica.';
  if(kind==='selection'&&(result?.decisions??[]).some((d:any)=>d.status==='outside'))return 'Verifica delle sole esclusioni; le fonti incerte restano incluse per la lettura di Sol.';
  if((result?.evidence??[]).some((e:any)=>(Array.isArray(e.issues)&&e.issues.length)||e.provenance==='external'||e.provenance==='general'))return 'Evidenze con problemi aperti o ricostruzioni da verificare.';
  if((result?.questions??[]).some((q:any)=>(q.format==='code'&&/explain|discuss|motiva|spiega|discut/i.test(String(q.text)))||(q.format==='open'&&/calculate|compute|calcola|determina/i.test(String(q.text))&&!/explain|why|motiva|spiega/i.test(String(q.text)))))return 'Il formato proposto non coincide con le operazioni richieste dal quesito.';
  if((result?.questions??[]).some((q:any)=>q.in_scope===false||q.format==='unknown'||/ambigu|incert|non (?:è )?chiar/i.test(String(q.scope_reason??''))))return 'Quesiti esclusi, ambigui o con formato da verificare.';
  return null;
}
export function sumUsage(calls:any[]){
  const values=calls.map(c=>c.usage).filter(Boolean);if(!values.length)return undefined;
  const result:any={cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}};
  for(const key of ['input','output','cacheRead','cacheWrite','reasoning','totalTokens'])result[key]=values.reduce((n,u)=>n+(u[key]??0),0);
  for(const key of Object.keys(result.cost))result.cost[key]=values.reduce((n,u)=>n+(u.cost?.[key]??0),0);
  return result;
}

import {preparationModelData} from './model-payload';

type Checkpoint={version:1,outline:any[],blocks:any[]};
const decode=(text:string)=>JSON.parse(text.trim().replace(/^```(?:json)?\s*|\s*```$/g,''));
function validateOutline(task:any,result:any,blocks:any[]){
 const outline=result?.outline;
 if(!Array.isArray(outline)||outline.length<3||outline.length>(task.chapter_limits?.max_blocks??48))throw Error('Indice di scrittura: servono da 3 a chapter_limits.max_blocks blocchi.');
 const ids=new Set<string>();
 for(const row of outline){
  if(!row||typeof row.id!=='string'||!row.id||ids.has(row.id)||!['text','activity'].includes(row.kind)||typeof row.title!=='string'||!row.title.trim()||typeof row.goal!=='string'||!row.goal.trim()||!['explain','worked','guided','independent','recap'].includes(row.role)||!Array.isArray(row.covers)||row.covers.some((i:any)=>!Number.isInteger(i)||i<0||i>=(task.chapter.exam_skills??[]).length))throw Error('Indice di scrittura: identità, ruolo, obiettivo o copertura non validi.');
  ids.add(row.id);
 }
 if(blocks.some((b:any,i:number)=>outline[i]?.id!==b.id||outline[i]?.kind!==b.kind))throw Error('Indice di scrittura: conserva tutti i blocchi recuperati, nello stesso ordine.');
 if(!outline.some((r:any)=>r.role==='explain'&&r.kind==='text')||!outline.some((r:any)=>r.role==='worked')||!outline.some((r:any)=>r.role==='independent'&&r.kind==='activity'))throw Error('Indice di scrittura: servono spiegazione, esempio svolto e prova autonoma.');
 const covered=new Set(outline.flatMap((r:any)=>r.covers));
 if((task.chapter.exam_skills??[]).some((_:any,i:number)=>!covered.has(i)))throw Error('Indice di scrittura: copri tutte le competenze del capitolo.');
 return outline;
}

/** Same immutable task and read receipts, bounded generation, no publication of partial chapters. */
export async function writeChapter(task:any,recovery:any,instructions:string,request:(prompt:string)=>Promise<string>,save:(value:Checkpoint)=>Promise<Checkpoint>,paused:()=>boolean){
 if(recovery?.error)throw Error('Il testo recuperato richiede una correzione prima della ripresa: '+recovery.error);
 let blocks:any[]=structuredClone(recovery?.blocks??[]),outline:any[]=structuredClone(recovery?.outline??[]);
 let continuing=false;
 const initial=()=>instructions+'\nScrivi il capitolo in richieste limitate. Prima restituisci SOLO JSON {outline:[{id,kind:"text"|"activity",title,goal,role:"explain"|"worked"|"guided"|"independent"|"recap",covers:number[]}]}. Progetta tutto il capitolo: covers usa gli indici da zero di chapter.exam_skills e ogni competenza deve essere coperta. Includi spiegazioni, esempi svolti e attività autonome, rispettando chapter_limits. I blocchi recuperati sono già completi: inserisci i loro ID e tipi all’inizio dell’indice nello stesso ordine, senza riscriverli. Pianifica solo le parti mancanti. Le eventuali fonti web verificate vanno in external_sources e come normali link nel testo; sources contiene soltanto passage ID del corso.\nBlocchi recuperati (dati):\n'+JSON.stringify(blocks)+'\nCompito (dati):\n'+JSON.stringify(preparationModelData(task));
 if(!outline.length){
  if(paused())return null;
  const base=initial();let error='';
  for(let attempt=0;;attempt++){
   try{
    const result=decode(await request(base+(error?'\nCorreggi il solo indice. Errore: '+error:'')));
    if(paused())return null;
    // Backwards-compatible complete responses still pass the ordinary whole-chapter validator.
    if(!result.outline&&Array.isArray(result.blocks)&&!blocks.length)return result;
    outline=validateOutline(task,result,blocks);break;
   }catch(e:any){if(attempt||paused()||(!/Indice di scrittura/.test(e.message)&&!(e instanceof SyntaxError)))throw e;error=e.message;}
  }
  ({outline,blocks}=await save({version:1,outline,blocks}));continuing=true;
 }else{
  outline=validateOutline(task,{outline},blocks);
  // A complete first block of an interrupted batch may have been recovered from its call record.
  ({outline,blocks}=await save({version:1,outline,blocks}));
 }
 while(blocks.length<outline.length){
  if(paused())return null;
  const pending=outline.slice(blocks.length,blocks.length+2);
  const preamble=continuing?'':instructions+'\nCompito (dati):\n'+JSON.stringify(preparationModelData(task))+'\nIndice del capitolo (dati):\n'+JSON.stringify(outline)+'\nBlocchi già salvati (dati):\n'+JSON.stringify(blocks)+'\n';
  const base=preamble+'Genera SOLO i blocchi richiesti, nello stesso ordine: '+JSON.stringify(pending)+'. Restituisci SOLO JSON {blocks:[blocchi_completi]}. Massimo due blocchi e 16000 caratteri JSON per risposta. Non restituire l’indice o blocchi precedenti. Rispetta gli ID, tipi, ruoli e obiettivi; usa il contesto già fornito senza ripetere le parti svolte. Il limite riguarda questa risposta, non la profondità complessiva del capitolo. Fonti esterne effettivamente lette in external_sources, mai in sources. Per amdahl verification.input usa processors e fraction=quota parallela; per gustafson processors e fraction=quota seriale. Prima di citare nuove fonti leggile con gli strumenti.';
  let error='';
  for(let attempt=0;;attempt++){
   try{
    const result=decode(await request(base+(error?'\nLa risposta è stata rifiutata; correggi soltanto questi blocchi: '+error:'')));
    if(paused())return null;
    if(!Array.isArray(result.blocks)||result.blocks.length!==pending.length||result.blocks.some((b:any,i:number)=>b.id!==pending[i].id||b.kind!==pending[i].kind))throw Error('Batch di scrittura: restituisci tutti e soli i blocchi richiesti, con gli stessi ID e tipi.');
    if(JSON.stringify(result).length>16000)throw Error('Batch di scrittura troppo lungo: massimo 16000 caratteri JSON.');
    ({outline,blocks}=await save({version:1,outline,blocks:[...blocks,...result.blocks]}));
    continuing=true;break;
   }catch(e:any){
    if(attempt||paused()||/Tempo limite|Subscription Sharing|usage.limit|quota|Provider interrotto/i.test(e.message))throw e;
    if(!(e instanceof SyntaxError)&&!/Batch di scrittura|Capitolo|font|Fonte|Citazione|Spiegazione|Esercizio|Prepara|Verifica|verifica|Ipotesi|Input|HTML|Identit|blocc|numerica/i.test(e.message))throw e;
    error=e.message;
   }
  }
 }
 return {blocks};
}

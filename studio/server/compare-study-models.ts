/** Isolated study-model evaluation: no course settings, attempts, or plans are modified. */
import {readFile,writeFile,mkdtemp,rm,mkdir} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import {ModelRuntime,createAgentSession,SessionManager,SettingsManager,DefaultResourceLoader} from '@earendil-works/pi-coding-agent';
const root=process.env.STUDIO_ROOT;if(!root)throw Error('STUDIO_ROOT richiesto.');
const python=process.env.STUDIO_PYTHON??path.join(root,'.state/slides-runtime/bin/python');
const models=(process.env.STUDIO_COMPARE_MODELS??'gpt-6-luna,gpt-5.6-terra,gpt-5.4-mini,gpt-6.1-sol').split(',');
const semantic=JSON.parse(await readFile(new URL('../tests/preparation-cases.json',import.meta.url),'utf8'));
const technical=JSON.parse(await readFile(new URL('../tests/model-comparison-cases.json',import.meta.url),'utf8'));
const cases=[...semantic.questions.map((x:any)=>({type:'question',...x})),...semantic.sources.map((x:any)=>({type:'source',...x}))];
const page=JSON.parse(execFileSync(python,['-c',`import sqlite3,json,sys
c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
r=c.execute("SELECT p.id,p.text,p.page,p.reserved,p.solution,d.issue FROM passages p JOIN documents d ON d.id=p.document WHERE p.id=?",('2bec55e42c15175560afd1aa:4',)).fetchone()
if not r or r['reserved'] or r['solution'] or r['issue'] or c.execute('SELECT 1 FROM protected_spans WHERE source=?',(r['id'],)).fetchone():raise ValueError('Evaluation page unavailable or protected')
print(json.dumps(dict(r)))`,path.join(root,'.state/studio/studio.sqlite3')],{encoding:'utf8'}));
const expectedExtract=Array.from(page.text.matchAll(/(?:^|\n)\s*([A-D])\.\s*([\s\S]*?)(?=\n\s*_{3,})/g),(m:any)=>({label:m[1],text:m[2].trim()}));
if(expectedExtract.length!==4)throw Error('Campione di estrazione non valido: servono 4 sottopunti annotati.');
const tasks=[
 {id:'classification',system:'Classifica SOLO i dati forniti. JSON {results:[{id,origin?,format?,scope?,status?}]}. Question: origin=exam|assigned|classroom|generated|administrative|solution|uncertain; format=open|numeric|code|mixed|choice|unknown; scope=in|out|uncertain. Source: status=relevant|prerequisite|outside|uncertain. Il perimetro prevale su nome/data. Domande del docente ed esercizi generati non sono esami autentici. Choice richiede opzioni esplicite. Una soluzione senza domanda ha formato unknown. Rispetta le incertezze. Non risolvere i problemi.',data:{scope:semantic.scope,items:cases.map(({expected,...item}:any)=>item)},gold:cases.map((c:any)=>({id:c.id,expected:c.expected}))},
 {id:'technical',system:'Rispondi ai problemi con JSON {results:[{id,answer,reason:string}]}. Rispetta esattamente ipotesi e tipo della risposta richiesto. Non aggiungere ipotesi implicite per rendere vera una risposta. Motivazione breve, massimo due frasi.',data:{items:technical.cases.map(({expected,...item}:any)=>item)},gold:technical.cases.map((c:any)=>({id:c.id,expected:{answer:c.expected}}))},
 {id:'extraction',system:'Estrai letteralmente tutti i sottopunti A-D dal PDF fornito. JSON {results:[{id:"A"|"B"|"C"|"D",text,source,format:"open"|"code"|"mixed"|"choice"|"numeric"|"unknown",in_scope:boolean,issues:string[]}]}. text deve copiare il testo originale del singolo sottopunto, inclusi punti e simboli, senza etichetta A./B./C./D. e senza righe per rispondere. Non tradurre, parafrasare o correggere una domanda ambigua. source deve essere il passage ID fornito. L’obiettivo è il primo parziale 2025-26: inclusi GPU/coalescing e memory consistency; esclusi heterogeneous systems/accelerators. Una formulazione tecnica incoerente va conservata e segnalata in issues; non inventare una soluzione. Non ci sono opzioni multiple in questa pagina.',data:{source:page.id,page:page.page,text:page.text},gold:expectedExtract.map((c:any)=>({id:c.label,expected:{text:c.text,source:page.id,format:'open',in_scope:c.label!=='D'}}))}
];
const reportPath=process.env.STUDIO_COMPARE_REPORT??path.join(root,'.state/studio/evaluations/model-comparison-'+Date.now()+'.json');
await mkdir(path.dirname(reportPath),{recursive:true});
const report:any={created:new Date().toISOString(),models,thinking:'medium',send:process.argv.includes('--send'),limitations:['One run per task and model, no statistical reliability estimate.','Two synthetic suites and one real non-reserved PDF page.','Token costs are SDK API-rate estimates, not money charged or measured subscription allowance.','No evaluation yet of full chapters, HTML activities or long agent tool-use.'],runs:[]};
if(!report.send){await writeFile(reportPath,JSON.stringify({...report,tasks:tasks.map(t=>({id:t.id,items:t.gold.length}))},null,2));console.log(JSON.stringify({preview:reportPath,sent:false}));process.exit(0);}
const runtime=await ModelRuntime.create();const available=await runtime.getAvailable();
const dir=await mkdtemp(path.join(os.tmpdir(),'study-model-comparison-'));
function equal(a:any,b:any):boolean{if(typeof b==='number')return typeof a==='number'&&Number.isFinite(a)&&Math.abs(a-b)<=1e-6*Math.max(1,Math.abs(b));if(Array.isArray(b))return Array.isArray(a)&&a.length===b.length&&b.every((v,i)=>equal(a[i],v));if(b&&typeof b==='object')return a&&typeof a==='object'&&Object.entries(b).every(([k,v])=>equal(a[k],v));return a===b;}
function quote(s:any){return typeof s==='string'?s.normalize('NFC').replace(/\s+/g,' ').trim():s;}
try{
 for(const id of models){
  const model=available.find(m=>m.provider==='openai'&&m.id===id);if(!model){report.runs.push({model:id,error:'Model not available in configured provider'});continue;}
  for(const task of tasks){
   const entry:any={model:id,task:task.id,total:task.gold.length,context:model.contextWindow,estimated_api_rates:model.cost};report.runs.push(entry);const began=Date.now();
   let output='',usage:any,error:any;
   const loader=new DefaultResourceLoader({cwd:dir,agentDir:dir,noExtensions:true,noSkills:true,noContextFiles:true,noPromptTemplates:true,noThemes:true,systemPrompt:task.system});await loader.reload();
   const {session}=await createAgentSession({cwd:dir,agentDir:dir,modelRuntime:runtime,model:{...model,maxTokens:Math.min(8192,model.maxTokens)},sessionManager:SessionManager.inMemory(),settingsManager:SettingsManager.inMemory({}),resourceLoader:loader,tools:[],customTools:[],thinkingLevel:'medium'});
   const unsubscribe=session.subscribe((e:any)=>{if(e.type==='message_start'&&e.message?.role==='assistant')output='';if(e.type==='message_update'&&e.assistantMessageEvent?.type==='text_delta')output+=e.assistantMessageEvent.delta;if(e.type==='message_end'&&e.message?.role==='assistant'){usage=e.message.usage;if(['error','aborted'].includes(e.message.stopReason))error=Error(e.message.errorMessage??e.message.stopReason);}});
   const timer=setTimeout(()=>void session.abort(),180000);
   try{
    await session.prompt(JSON.stringify(task.data));if(error)throw error;
    const actual=JSON.parse(output.trim().replace(/^```(?:json)?\s*|\s*```$/g,''));if(!Array.isArray(actual.results))throw Error('Missing results array');
    entry.results=task.gold.map((g:any)=>{const found=actual.results.filter((x:any)=>x.id===g.id);const a=found[0];const checks=Object.entries(g.expected).map(([k,v])=>({field:k,pass:k==='text'?quote(a?.[k])===quote(v):equal(a?.[k],v)}));return {id:g.id,expected:g.expected,actual:a,checks,pass:found.length===1&&checks.every(x=>x.pass)};});
    entry.extra_ids=actual.results.filter((x:any)=>!task.gold.some((g:any)=>g.id===x.id)).map((x:any)=>x.id);entry.passed=entry.results.filter((x:any)=>x.pass).length;entry.valid_json=true;entry.status='completed';
   }catch(e:any){entry.error=String(e.message);entry.output=output;entry.passed=null;entry.status=/not.supported|not.available|not.found|access.*denied/i.test(entry.error)?'unavailable':'error';}
   finally{clearTimeout(timer);unsubscribe();session.dispose();entry.elapsed_ms=Date.now()-began;entry.usage=usage;await writeFile(reportPath,JSON.stringify(report,null,2));}
   console.log(JSON.stringify({model:id,task:task.id,passed:entry.passed,total:entry.total,elapsed_ms:entry.elapsed_ms,error:entry.error}));
   if(entry.error&&/Subscription Sharing|usage.limit|authentication|not.supported|not.available|not.found|access.*denied/i.test(entry.error))break;
  }
 }
}finally{await rm(dir,{recursive:true,force:true});await writeFile(reportPath,JSON.stringify(report,null,2));}
console.log(JSON.stringify({report:reportPath}));

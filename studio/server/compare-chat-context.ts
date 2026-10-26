/** Bounded evaluation only: real context read through SQLite mode=ro, private report, no app mutations. */
import {execFileSync} from 'node:child_process';
import {mkdtemp,mkdir,writeFile,rm} from 'node:fs/promises';
import path from 'node:path';import os from 'node:os';
import {Type} from '@sinclair/typebox';
import {ModelRuntime,createAgentSession,SessionManager,SettingsManager,DefaultResourceLoader,estimateTokens} from '@earendil-works/pi-coding-agent';
import {SYSTEM} from './tutor';
import {compactChatContext,readChatContext} from './chat-context';
import {deduplicateSourceTexts,preparationModelData} from './model-payload';
import {sumUsage} from './model-routing';
import {promptWithDeadline} from './preparation-deadline';
import {syntheticChatSnapshot} from '../tests/fixtures/chat-context';
const real=process.argv.includes('--real-context'),validation=process.argv.includes('--validation'),root=process.env.STUDIO_ROOT;
if(real&&!root)throw Error('STUDIO_ROOT richiesto per anteprima reale.');
if(real&&process.argv.includes('--send')&&!process.argv.includes('--allow-real-data'))throw Error('Serve --allow-real-data dopo autorizzazione esplicita dell’utente.');
const python=process.env.STUDIO_PYTHON??path.join(root??'', '.state/slides-runtime/bin/python');
const snapshot=real?JSON.parse(execFileSync(python,['-B','-c',`
import sqlite3,json,sys,re
from pathlib import Path
from polimi_lectures.study import Study
s=Study.__new__(Study);s.root=Path(sys.argv[1]);s.state=s.root/'.state/studio';s.db=sqlite3.connect('file:'+str(s.state/'studio.sqlite3')+'?mode=ro',uri=True);s.db.row_factory=sqlite3.Row
p='a2c99b87213548a4a412e8da88e2102b';sid='10cfd8a1c1804f899e75a7ccc82b91db'
context=s.context(sid);refs=set()
def gather(v):
 if isinstance(v,dict):
  for k,x in v.items():
   if k=='sources' and isinstance(x,list):refs.update(t for t in x if isinstance(t,str))
   gather(x)
 elif isinstance(v,list):
  for x in v:gather(x)
 elif isinstance(v,str):refs.update(re.findall(r'source:([a-f0-9]{24}:\\d+)',v))
gather(context);sources={}
for ref in refs:
 try:
  src=s.source(ref,allow_reserved=False,allow_solutions=False)
  if not s.db.execute('SELECT 1 FROM protected_spans WHERE source=?',(ref,)).fetchone():sources[ref]=src
 except ValueError:pass
samples=[]
for kind in ['chapter','map','review_didactic']:
 row=s.db.execute('SELECT input FROM prep_tasks WHERE path=? AND kind=? ORDER BY rowid DESC LIMIT 1',(p,kind)).fetchone()
 if row:samples.append({'kind':kind,'data':json.loads(row[0])})
r=s.db.execute('SELECT id FROM attempts WHERE session=? ORDER BY rowid DESC LIMIT 1',(sid,)).fetchone()
if r:
 a=s.assessment(sid,r[0]);samples.append({'kind':'assessment','data':{'question':a['activity']['spec']['prompt'],'rubric':a['activity']['spec'].get('rubric'),'answer':a['attempt']['answer'],'sources':a['sources'],'solution':a['activity']['spec'].get('solution')}})
print(json.dumps({'context':context,'sources':sources,'samples':samples,'model':s.setting('model')}))
`,root!],{cwd:path.resolve(import.meta.dirname,'../..'),encoding:'utf8',maxBuffer:20*1024*1024})):syntheticChatSnapshot();
const size=(data:any)=>JSON.stringify(data).length;
const estimated=(data:any)=>estimateTokens({role:'user',content:[{type:'text',text:JSON.stringify(data)}],timestamp:Date.now()} as any);
const reportPath=process.env.STUDIO_COMPARE_REPORT??path.resolve(import.meta.dirname,'../../.state/evaluations/chat-context-'+(real?'real':'synthetic')+(validation?'-validation':'')+'.json');
await mkdir(path.dirname(reportPath),{recursive:true});
const report:any={created:new Date().toISOString(),data:real?'real-course-readonly-user-authorized':'synthetic-generated-no-user-data',send:process.argv.includes('--send'),model:snapshot.model,limits:{final_turns:validation?6:12,tools_per_turn:4,turn_timeout_ms:120000},limitations:['One run per condition and scenario: not a statistical regression guarantee.',real?'User authorized sending the real course context to the configured model; preference changes are synthetic.':'Generated data only; similar length does not imply identical difficulty.','Two sessions with three turns each, same real snapshot, synthetic preference changes.','Read-only evaluation uses the tutor system instructions but only read_context and read_source tools; it does not reproduce every production feature.','Usage includes assistant/tool-loop responses and compaction usage when provided by the SDK; events with no usage are flagged as missing.','SDK price estimates are not billed amounts or measured subscription allowance.','Primary question: conservative retrieval of other plan chapters and exam questions; current chapter, scope, diary, preferences, attempts and events remain complete.'],payload_samples:snapshot.samples.map(({kind,data}:any)=>{const optimized=kind==='assessment'?deduplicateSourceTexts(data):preparationModelData(data);return {kind,before_chars:size(data),after_chars:size(optimized),before_estimated_tokens:estimated(data),after_estimated_tokens:estimated(optimized)};}),initial_context:{full_chars:size(snapshot.context),compact_chars:size(compactChatContext(snapshot.context)),full_estimated_tokens:estimated(snapshot.context),compact_estimated_tokens:estimated(compactChatContext(snapshot.context))},runs:[]};
const save=()=>writeFile(reportPath,JSON.stringify(report,null,2),{mode:0o600});
await save();
if(!report.send){console.log(JSON.stringify({report:reportPath,sent:false,payload_samples:report.payload_samples,context:report.initial_context}));process.exit(0);}
const selected=snapshot.model??{provider:'openai',id:'gpt-6.1-sol'};
const runtime=await ModelRuntime.create(),available=await runtime.getAvailable();
const model=available.find(m=>m.provider===selected.provider&&m.id===selected.id);if(!model)throw Error('Modello selezionato non disponibile.');
report.model={provider:model.provider,id:model.id,contextWindow:model.contextWindow,cost:model.cost};
const dir=await mkdtemp(path.join(os.tmpdir(),'chat-context-comparison-'));
const other=snapshot.context.curriculum.plan.data.chapters.find((c:any)=>c.id!==snapshot.context.curriculum.chapter?.chapter&&c.id.startsWith('pc03'));
if(!other)throw Error('Capitolo di confronto mancante.');
const firstQuestion=snapshot.context.curriculum.exam_profile.questions[0];
const scenarios=validation?[[
 {id:'confirmed_scope',question:'Spiega lo stato attuale del mio percorso: devo ancora confermarne il perimetro? Le API OpenMP sono incluse? SOLO JSON {confirmed:boolean,needs_confirmation:boolean,included:boolean,reason:string}. Distingui stato attuale e vecchie note.',expected:{confirmed:true,needs_confirmation:false,included:false}},
 {id:'exam_question',question:'Trascrivi letteralmente il primo quesito del profilo di esame e tutti i suoi passage ID in sources. Non ricostruirlo per somiglianza. SOLO JSON {text:string,sources:string[]}.',expected:{text:firstQuestion.text,sources:firstQuestion.sources}},
 {id:'updated_question',updated_question:'RETTIFICA SINTETICA DI TEST: questo è il testo corrente del primo quesito; il codice di controllo è R7-K42. Non usare la versione precedente.',question:'Il profilo è stato aggiornato: trascrivi letteralmente il testo attuale del primo quesito e i suoi passage ID. SOLO JSON {text:string,sources:string[]}. Recupera lo stato corrente, non la versione dei turni precedenti.',expected:{text:'RETTIFICA SINTETICA DI TEST: questo è il testo corrente del primo quesito; il codice di controllo è R7-K42. Non usare la versione precedente.',sources:firstQuestion.sources}},
]]:[[
 {id:'metrics',question:'La relazione E_p=SU_p/p vale sempre nel corso? Rispondi SOLO JSON {speedup_baseline:"T*"|"T1",efficiency_baseline:"T*"|"T1",requires_equality:boolean,explanation:string}. Motivazione breve con definizioni e ipotesi.',expected:{speedup_baseline:'T*',efficiency_baseline:'T1',requires_equality:true}},
 {id:'scope',question:'Le API OpenMP sono incluse nel primo parziale del mio percorso confermato? SOLO JSON {included:boolean,reason:string,citations:string[]}. Usa il perimetro del percorso, distinguendolo dai vecchi temi.',expected:{included:false}},
 {id:'other_chapter',question:'Per il capitolo '+other.id+' trascrivi esattamente il campo assessment del piano e i suoi primi due passage ID in sources. Non ricostruirli dalla memoria. SOLO JSON {assessment:string,sources:string[]}.',expected:{assessment:other.assessment,sources:other.sources.slice(0,2)}},
],[
 {id:'preference',preference:'Preferenza esplicita per questo esperimento: usa esempi con otto importi interi; evita analogie sportive.',question:'Quale esempio numerico ho chiesto e quale analogia ho escluso nelle mie preferenze attuali? SOLO JSON {example_size:number,avoid:"sport"|"cucina",explanation:string}.',expected:{example_size:8,avoid:'sport'}},
 {id:'updated_preference',preference:'RETTIFICA esplicita: sostituisce la precedente preferenza su otto importi e sport. Usa esempi con diciassette importi interi; evita analogie di cucina.',question:'Riprendi le mie preferenze aggiornate: quale dimensione di esempio e quale analogia evitare? SOLO JSON {example_size:number,avoid:"sport"|"cucina",explanation:string}.',expected:{example_size:17,avoid:'cucina'}},
 {id:'missing_data',question:'Qual è il valore numerico esatto di T* per un mio nuovo algoritmo? Non ti ho fornito né algoritmo, né input, né modello dei costi. SOLO JSON {known:boolean,value:number|null,explanation:string}. Non usare al suo posto i valori degli esempi del capitolo.',expected:{known:false,value:null}},
]];
function matches(actual:any,expected:any):boolean{return Object.entries(expected).every(([k,v])=>JSON.stringify(actual?.[k])===JSON.stringify(v));}
let blocked=false;
try{
 for(let group=0;group<scenarios.length&&!blocked;group++)for(const strategy of group?['compact','full']:['full','compact']){
  if(blocked)break;
  let current=structuredClone(snapshot.context),active:any;
  const tools=[
   {name:'read_context',label:'read_context',description:'Recupera integralmente il capitolo del piano indicato, i quesiti del profilo o tutto lo stato corrente. Usa i dettagli del piano quando richiesti. Non modifica dati.',parameters:Type.Object({section:Type.Union([Type.Literal('plan_chapter'),Type.Literal('exam_questions'),Type.Literal('full_context')]),chapter:Type.Optional(Type.String()),offset:Type.Optional(Type.Number())}),async execute(_id:string,p:any){if(active.tools.length>=4)throw Error('Limite di quattro letture per turno.');const result=readChatContext(current,p);active.tools.push({name:'read_context',args:p,characters:size(result)});return {content:[{type:'text' as const,text:JSON.stringify(result)}],details:{}};}},
   {name:'read_source',label:'read_source',description:'Leggi una fonte originale del corso già disponibile nel percorso, con ID, testo e metadati.',parameters:Type.Object({id:Type.String()}),async execute(_id:string,p:any){if(active.tools.length>=4)throw Error('Limite di quattro letture per turno.');const result=snapshot.sources[p.id];if(!result)throw Error('Fonte non disponibile per questo confronto.');active.tools.push({name:'read_source',args:p,characters:size(result)});return {content:[{type:'text' as const,text:JSON.stringify(result)}],details:{}};}},
  ];
  const loader=new DefaultResourceLoader({cwd:dir,agentDir:dir,noExtensions:true,noSkills:true,noContextFiles:true,noPromptTemplates:true,noThemes:true,systemPrompt:SYSTEM+'\nValutazione isolata in sola lettura. Non modificare percorso, diario o attività. Usa soltanto gli strumenti di lettura disponibili. Lo stato aggiornato di ogni turno prevale su stati precedenti, soprattutto per rettifiche e preferenze. Rispetta il formato JSON richiesto, con spiegazioni brevi.'});await loader.reload();
  const {session}=await createAgentSession({cwd:dir,agentDir:dir,modelRuntime:runtime,model:{...model,maxTokens:4096},resourceLoader:loader,sessionManager:SessionManager.inMemory(),settingsManager:SettingsManager.inMemory({retry:{enabled:false,provider:{maxRetries:0}}}),tools:tools.map(t=>t.name),customTools:tools,thinkingLevel:'medium'});
  let output='',error:Error|undefined;
  const unsubscribe=session.subscribe((event:any)=>{
   if(event.type==='message_start'&&event.message?.role==='assistant')output='';
   if(event.type==='message_update'&&event.assistantMessageEvent?.type==='text_delta')output+=event.assistantMessageEvent.delta;
   if(event.type==='message_end'&&event.message?.role==='assistant'){if(event.message.usage)active.calls.push({usage:event.message.usage});if(['error','aborted'].includes(event.message.stopReason))error=Error(event.message.errorMessage??'Provider interrupted');}
   if(event.type==='compaction_end'){active.compactions.push({reason:event.reason,error:event.errorMessage,usage:event.result?.usage});if(event.result?.usage)active.calls.push({kind:'compaction',usage:event.result.usage});}
  });
  try{
   for(const scenario of scenarios[group]){
    if('updated_question' in scenario)current.curriculum.exam_profile.questions[0].text=scenario.updated_question;
    if('preference' in scenario)current.curriculum.preferences=[{id:'evaluation-preference',kind:'preference',text:scenario.preference,evidence:['evaluation-message']}];
    active={strategy,group,id:scenario.id,expected:scenario.expected,tools:[],calls:[],compactions:[]};report.runs.push(active);output='';error=undefined;
    const data=strategy==='compact'?compactChatContext(current):current;
    const prompt='Stato aggiornato (dati):\n'+JSON.stringify(data)+'\n\nRichiesta dello studente:\n'+scenario.question;
    active.initial_characters=prompt.length;const began=Date.now();
    try{await promptWithDeadline(session,prompt,120000);if(error)throw error;active.actual=JSON.parse(output.trim().replace(/^```(?:json)?\s*|\s*```$/g,''));active.pass=matches(active.actual,scenario.expected);}
    catch(e:any){active.error=e.message;active.output=output;active.pass=false;if(/Subscription Sharing|usage.limit|quota|authentication/i.test(e.message))blocked=true;}
    active.elapsed_ms=Date.now()-began;active.usage=sumUsage(active.calls);await save();
    console.log(JSON.stringify({strategy,group,id:scenario.id,pass:active.pass,tools:active.tools.length,tokens:active.usage?.totalTokens,cost:active.usage?.cost?.total,ms:active.elapsed_ms,error:active.error}));
    if(blocked||active.error)break;
   }
  }finally{unsubscribe();session.dispose();}
 }
}finally{await rm(dir,{recursive:true,force:true});await save();}
report.summary=['full','compact'].map(strategy=>{
 const runs=report.runs.filter((r:any)=>r.strategy===strategy);return {strategy,turns:runs.length,passed:runs.filter((r:any)=>r.pass).length,tool_calls:runs.reduce((n:number,r:any)=>n+r.tools.length,0),model_calls:runs.reduce((n:number,r:any)=>n+r.calls.length,0),compactions:runs.reduce((n:number,r:any)=>n+r.compactions.length,0),elapsed_ms:runs.reduce((n:number,r:any)=>n+r.elapsed_ms,0),usage:sumUsage(runs.flatMap((r:any)=>r.calls))};
});await save();console.log(JSON.stringify({report:reportPath,summary:report.summary}));

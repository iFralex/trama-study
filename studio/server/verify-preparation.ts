/** Annotated semantic benchmark. Preview is local; --send explicitly invokes the selected provider. */
import {readFile,writeFile,mkdtemp,rm} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import os from 'node:os';
import {ModelRuntime,createAgentSession,SessionManager,SettingsManager,DefaultResourceLoader} from '@earendil-works/pi-coding-agent';
const fixture=JSON.parse(await readFile(new URL('../tests/preparation-cases.json',import.meta.url),'utf8'));
const items=[...fixture.questions.map((x:any)=>({type:'question',...x})),...fixture.sources.map((x:any)=>({type:'source',...x}))];
const payload=items.map(({expected,...item}:any)=>item);
const preview=process.env.STUDIO_VERIFY_PAYLOAD??path.join(os.tmpdir(),'preparation-semantic-payload.json');
await writeFile(preview,JSON.stringify({scope:fixture.scope,items:payload},null,2));
if(!process.argv.includes('--send')){console.log(JSON.stringify({preview,questions:fixture.questions.length,sources:fixture.sources.length,sent:false}));process.exit(0);}
const root=process.env.STUDIO_ROOT;if(!root)throw Error('STUDIO_ROOT richiesto.');
const python=process.env.STUDIO_PYTHON??path.join(root,'.state/slides-runtime/bin/python');
const selected=JSON.parse(execFileSync(python,['-c',"import sqlite3,json,sys;d=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True);r=d.execute(\"SELECT value FROM settings WHERE key='model'\").fetchone();print(r[0] if r else 'null')",path.join(root,'.state/studio/studio.sqlite3')],{encoding:'utf8'}));
const runtime=await ModelRuntime.create();const available=await runtime.getAvailable();const model=available.find(m=>m.provider===selected?.provider&&m.id===selected?.id);if(!model)throw Error('Modello configurato non disponibile.');
const directory=await mkdtemp(path.join(os.tmpdir(),'preparation-semantic-'));
const report:any={created:new Date().toISOString(),provider:model.provider,model:model.id,sample:fixture.notice,runs:[]};
try{
  for(const mode of process.argv.includes('--compare')?['small','wide']:['wide']){
    const batches:any[][]=[];let batch:any[]=[],size=0;const budget=mode==='small'?6000:96000;
    for(const item of payload){const length=JSON.stringify(item).length;if(batch.length&&size+length>budget){batches.push(batch);batch=[];size=0;}batch.push(item);size+=length;}if(batch.length)batches.push(batch);
    const predicted:any[]=[];const began=Date.now();
    for(const items of batches){
      const loader=new DefaultResourceLoader({cwd:directory,agentDir:directory,noExtensions:true,noSkills:true,noContextFiles:true,noPromptTemplates:true,noThemes:true,systemPrompt:'Classifica soltanto i dati forniti. Restituisci SOLO JSON {results:[{id,origin?,format?,scope?,status?}]}. Per question: origin=exam|assigned|classroom|generated|administrative|solution|uncertain, format=open|numeric|code|mixed|choice|unknown, scope=in|out|uncertain. Per source: status=relevant|prerequisite|outside|uncertain. Il perimetro prevale su data e nome. Domande del docente/esercizi AI non sono esami autentici. Choice richiede opzioni esplicite. Unknown non va trasformato in certezza. Una soluzione senza domanda ha format unknown. Considera prerequisite le basi necessarie e outside i documenti amministrativi. La provenienza originale verificata exam attesta l’origine; full può contenere quesiti pertinenti. Non risolvere gli esercizi.'});await loader.reload();
      const {session}=await createAgentSession({cwd:directory,agentDir:directory,modelRuntime:runtime,model:{...model,maxTokens:8192},sessionManager:SessionManager.inMemory(),settingsManager:SettingsManager.inMemory({}),resourceLoader:loader,tools:[],customTools:[],thinkingLevel:'medium'});
      let output='',error:any;const unsubscribe=session.subscribe((event:any)=>{if(event.type==='message_start'&&event.message?.role==='assistant')output='';if(event.type==='message_update'&&event.assistantMessageEvent?.type==='text_delta')output+=event.assistantMessageEvent.delta;if(event.type==='message_end'&&['error','aborted'].includes(event.message?.stopReason))error=Error(event.message.errorMessage??'Provider interrotto');});const timer=setTimeout(()=>void session.abort(),300000);
      try{await session.prompt(JSON.stringify({scope:fixture.scope,items}));if(error)throw error;predicted.push(...JSON.parse(output.trim().replace(/^```(?:json)?\s*|\s*```$/g,'')).results);}finally{clearTimeout(timer);unsubscribe();session.dispose();}
    }
    const results=items.map((expected:any)=>{const found=predicted.filter(p=>p.id===expected.id);const actual=found[0];return {id:expected.id,expected:expected.expected,actual,pass:found.length===1&&Object.entries(expected.expected).every(([key,value])=>actual?.[key]===value)};});
    report.runs.push({mode,requests:batches.length,elapsed_ms:Date.now()-began,passed:results.filter((r:any)=>r.pass).length,total:results.length,results});
    console.log(JSON.stringify({mode,requests:batches.length,passed:results.filter((r:any)=>r.pass).length,total:results.length}));
  }
}finally{await rm(directory,{recursive:true,force:true});}
const output=process.env.STUDIO_VERIFY_REPORT??path.join(os.tmpdir(),'preparation-semantic-report.json');await writeFile(output,JSON.stringify(report,null,2));
if(report.runs.some((r:any)=>r.passed!==r.total))process.exitCode=1;

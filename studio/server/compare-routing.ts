/** Paired real-source routing comparison. Read-only course access, no preparation writes. */
import {writeFile,mkdtemp,mkdir,rm} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import path from 'node:path';import os from 'node:os';
import {ModelRuntime,createAgentSession,SessionManager,SettingsManager,DefaultResourceLoader} from '@earendil-works/pi-coding-agent';
import {SELECTION_SYSTEM,selectionPacket,validateDecisions,exclusionReview,mergeExclusions} from './selection';
import {sumUsage} from './model-routing';
const root=process.env.STUDIO_ROOT;if(!root)throw Error('STUDIO_ROOT richiesto.');
const python=process.env.STUDIO_PYTHON??path.join(root,'.state/slides-runtime/bin/python');
const validation=process.argv.includes('--validation');
const annotated=validation?[
 ['c322f95fad43124a7f2b9686:11',['relevant'],'Politiche PRAM concurrent write.'],
 ['f4e8ac8af47b828c9d5dd225:31',['relevant'],'CUDA execution model host/device.'],
 ['c3599b0cde41cdb23952a604:32',['relevant','uncertain'],'Relaxed consistency/fences: mantenere il contesto concettuale; non confondere con implementing locks escluso.'],
 ['f649486dbacc8992411b4da3:15',['outside'],'API Pthreads esplicitamente escluse.'],
 ['f649486dbacc8992411b4da3:31',['outside'],'Direttive OpenMP e implementazione Pthreads esplicitamente escluse.'],
 ['603d0e418009bd364807bf15:3',['outside'],'Metodologia PCAM esplicitamente esclusa.'],
] as const:[
 ['8a8142f839c01aa49d556911:0',['outside'],'Solo organizzazione aula.'],
 ['834451b226ccc25679c49cf2:60',['outside','uncertain'],'Risorse pratiche/organizzazione, non insegna CUDA; ammissibile conservare il dubbio.'],
 ['b6df667b26598cf124184518:0',['relevant'],'Recap PRAM e simulazione del modello.'],
 ['b6df667b26598cf124184518:348',['relevant'],'Weak/strong scaling e misurazione elapsed time.'],
 ['ea57158bc293dddadbd48da9:0',['relevant','uncertain'],'PRAM: terminologia trascritta male, da conservare.'],
 ['ea57158bc293dddadbd48da9:420',['relevant'],'Amdahl, quota seriale.'],
 ['6d2004724db9e5ea899ffd75:0',['relevant'],'Modello data parallel, rapporto software/hardware.'],
 ['6d2004724db9e5ea899ffd75:396',['relevant'],'Banda memoria e ALU.'],
 ['8f8051996aa8dabb39568afb:0',['relevant'],'Sequential consistency.'],
 ['8f8051996aa8dabb39568afb:60',['relevant','uncertain'],'TSO: dubbio di notazione non esclude l’argomento.'],
 ['8f8051996aa8dabb39568afb:108',['relevant','uncertain'],'Contenuto misto ma include SC for DRF esplicitamente richiesto.'],
 ['9335ec185c9a063f1dbf595e:0',['outside','uncertain'],'Introduzione metodologia del blocco esplicitamente escluso; recap ammette dubbio.'],
 ['9335ec185c9a063f1dbf595e:264',['outside'],'Agglomeration/mapping PCAM, blocco escluso, non semplice CUDA.'],
 ['7446ba66411cc6eb25bb6f25:0',['outside'],'Sola organizzazione esame.'],
 ['7446ba66411cc6eb25bb6f25:312',['relevant','uncertain'],'Esercitazione prefix scan CUDA: conservare anche se dopo confine lezioni.'],
] as const;
const snapshot=JSON.parse(execFileSync(python,['-c',`import sqlite3,json,sys
c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
ids=json.loads(sys.argv[2]);sources=[]
for sid in ids:
 r=c.execute('SELECT p.*,d.issue FROM passages p JOIN documents d ON d.id=p.document WHERE p.id=?',(sid,)).fetchone()
 if not r or r['reserved'] or r['solution'] or r['issue'] or c.execute('SELECT 1 FROM protected_spans WHERE source=?',(sid,)).fetchone():raise ValueError('Source unavailable or protected: '+sid)
 sources.append({k:r[k] for k in ('id','title','text','page','start','end','kind','quality')})
p=c.execute('SELECT objective FROM course_paths WHERE id=?',('a2c99b87213548a4a412e8da88e2102b',)).fetchone()
print(json.dumps({'sources':sources,'objective':json.loads(p[0])}))`,path.join(root,'.state/studio/studio.sqlite3'),JSON.stringify(annotated.map(x=>x[0]))],{encoding:'utf8'}));
const batches=(validation?[snapshot.sources]:[snapshot.sources.filter((_:any,i:number)=>i%2===0),snapshot.sources.filter((_:any,i:number)=>i%2===1)]).map((sources:any[])=>selectionPacket({title:'Campione trasversale fonti originali',objective:snapshot.objective,previews:sources.map(({text,...s}:any)=>({...s,preview:text,truncated:false}))}));
const reportPath=process.env.STUDIO_COMPARE_REPORT??path.join(root,'.state/studio/evaluations/routing-comparison-'+Date.now()+'.json');await mkdir(path.dirname(reportPath),{recursive:true});
const report:any={created:new Date().toISOString(),send:process.argv.includes('--send'),thinking:'medium',validation,system:SELECTION_SYSTEM,annotations:annotated,batches,limitations:[validation?'Six previously unused real PDF pages, one run per strategy; no statistical guarantee.':'15 real passages, two repeated runs; not a statistical estimate or full-course evaluation.','Acceptable label sets were annotated before requests; uncertainty retains sources for expert deep reading.','Estimated API-equivalent costs include all worker/expert calls; actual subscription allowance is not observable.','Both strategies use the same bounded prompt and no tools. This compares routing, not the old unbounded pipeline.'],runs:[]};
await writeFile(reportPath,JSON.stringify(report,null,2));if(!report.send){console.log(JSON.stringify({preview:reportPath,sent:false}));process.exit(0);}
const runtime=await ModelRuntime.create(),available=await runtime.getAvailable(),dir=await mkdtemp(path.join(os.tmpdir(),'study-routing-'));
async function ask(id:string,packet:any,run:any){
 const model=available.find(m=>m.provider==='openai'&&m.id===id);if(!model)throw Error('Modello non disponibile: '+id);
 let output='',error:Error|undefined;const messages:any[]=[];const began=Date.now();
 const loader=new DefaultResourceLoader({cwd:dir,agentDir:dir,noExtensions:true,noSkills:true,noContextFiles:true,noPromptTemplates:true,noThemes:true,systemPrompt:SELECTION_SYSTEM});await loader.reload();
 const {session}=await createAgentSession({cwd:dir,agentDir:dir,modelRuntime:runtime,model:{...model,maxTokens:Math.min(8192,model.maxTokens)},sessionManager:SessionManager.inMemory(),settingsManager:SettingsManager.inMemory({}),resourceLoader:loader,tools:[],customTools:[],thinkingLevel:'medium'});
 const unsub=session.subscribe((e:any)=>{if(e.type==='message_start'&&e.message?.role==='assistant')output='';if(e.type==='message_update'&&e.assistantMessageEvent?.type==='text_delta')output+=e.assistantMessageEvent.delta;if(e.type==='message_end'&&e.message?.role==='assistant'){if(e.message.usage)messages.push({usage:e.message.usage});if(['error','aborted'].includes(e.message.stopReason))error=Error(e.message.errorMessage??e.message.stopReason);}});
 const timer=setTimeout(()=>void session.abort(),180000);
 try{await session.prompt('Compito (dati):\n'+JSON.stringify(packet));if(error)throw error;return validateDecisions(packet,JSON.parse(output.trim().replace(/^```(?:json)?\s*|\s*```$/g,'')));}
 catch(e:any){error=e;throw e;}
 finally{clearTimeout(timer);unsub();session.dispose();run.calls.push({model:id,items:packet.previews.map((s:any)=>s.id),usage:sumUsage(messages),elapsed_ms:Date.now()-began,output,error:error?.message});await writeFile(reportPath,JSON.stringify(report,null,2));}
}
try{
 for(let repeat=0;repeat<(validation?1:2);repeat++)for(let i=0;i<batches.length;i++)for(const strategy of repeat?['hybrid','sol']:['sol','hybrid']){
  const task=batches[i],run:any={repeat,batch:i,strategy,calls:[]};report.runs.push(run);
  try{
   let result=await ask(strategy==='sol'?'gpt-6.1-sol':'gpt-6-luna',task,run);
   if(strategy==='hybrid'){run.worker_result=result;const review=exclusionReview(task,result);if(review)result=mergeExclusions(task,result,await ask('gpt-6.1-sol',review,run));}
   run.result=result;run.checks=result.decisions.map((d:any)=>{const a=annotated.find(x=>x[0]===d.source)!;return {source:d.source,actual:d.status,accepted:a[1],pass:(a[1] as readonly string[]).includes(d.status),critical_omission:d.status==='outside'&&!(a[1] as readonly string[]).includes('outside')};});
   run.passed=run.checks.filter((c:any)=>c.pass).length;run.critical_omissions=run.checks.filter((c:any)=>c.critical_omission).length;
  }catch(e:any){run.error=e.message;}
  run.usage=sumUsage(run.calls);await writeFile(reportPath,JSON.stringify(report,null,2));console.log(JSON.stringify({strategy,repeat,batch:i,passed:run.passed,total:task.previews.length,calls:run.calls.length,cost:run.usage?.cost.total,error:run.error}));
 }
}finally{await rm(dir,{recursive:true,force:true});await writeFile(reportPath,JSON.stringify(report,null,2));}
const totals=['sol','hybrid'].map(strategy=>{
 const runs=report.runs.filter((r:any)=>r.strategy===strategy),usage=sumUsage(runs.flatMap((r:any)=>r.calls));
 return {strategy,passed:runs.reduce((n:number,r:any)=>n+(r.passed??0),0),critical_omissions:runs.reduce((n:number,r:any)=>n+(r.critical_omissions??0),0),qualified:runs.length===(validation?1:4)&&runs.every((r:any)=>!r.error&&r.checks?.every((c:any)=>c.pass)&&r.calls.every((c:any)=>c.usage?.cost&&Number.isFinite(c.usage.cost.total))),usage,elapsed_ms:runs.flatMap((r:any)=>r.calls).reduce((n:number,c:any)=>n+c.elapsed_ms,0)};
});
const qualified=totals.filter(t=>t.qualified).sort((a,b)=>a.usage.cost.total-b.usage.cost.total);
report.comparison={totals,least_estimated_cost_qualified:qualified[0]?.strategy??null,scope:'This sample only; not measured subscription allowance.'};
await writeFile(reportPath,JSON.stringify(report,null,2));console.log(JSON.stringify({report:reportPath,comparison:report.comparison}));

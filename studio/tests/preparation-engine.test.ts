import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtemp,rm} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import {ModelRuntime} from '@earendil-works/pi-coding-agent';
import {Bridge} from '../server/bridge';
import {Tutor} from '../server/tutor';
import {CourseEngine} from '../server/course-engine';
import {sourceBudget,preparationInstructions} from '../server/preparation-engine';
const python=process.env.STUDIO_PYTHON??'/Volumes/ORICO/polimi-lectures/.state/slides-runtime/bin/python';
async function idle(engine:CourseEngine,id:string){const until=Date.now()+30000;while(engine.jobs.has(id)){if(Date.now()>until)throw Error('Worker did not finish');await new Promise(r=>setTimeout(r,20));}}

test('budgets preserve response/tool space and cap default source input',()=>{
  assert.equal(sourceBudget({contextWindow:262144,maxTokens:32768},2500),32000);
  assert.ok(sourceBudget({contextWindow:16384,maxTokens:8192},2000)<4000);
  assert.match(preparationInstructions('selection'),/uncertain/);
  assert.match(preparationInstructions('review_discipline'),/checked_blocks/);
});

async function selectivePipeline(hybrid=false,quota=false,resumeExpert=false,chunked=false){
  const root=await mkdtemp(path.join(os.tmpdir(),'studio-selective-')),project=path.resolve(import.meta.dirname,'../..');
  execFileSync(python,['-c',`import sys,pymupdf
from pathlib import Path
p=Path(sys.argv[1])/'corsi'/'general-course-2026'/'materiali';p.mkdir(parents=True)
for name,text in [('lecture.pdf','An algorithm has ordered instructions. PRAM uses processors and shared memory. EREW forbids concurrent reads and writes.'),('exam-training.pdf','Exercise 1. Explain the difference between EREW and CREW. Motivate your answer.'),('exam-heldout.pdf','HOLDOUT_SECRET: explain a fresh algorithm.'),('exam-heldout.sol.pdf','HOLDOUT_SOLUTION_SECRET')]:
 d=pymupdf.open();pg=d.new_page();pg.insert_text((30,40),text);d.save(p/name);d.close()`,root]);
  const bridge=new Bridge(python,project,root);const payloads:any[]=[],phases:string[]=[],trace:{kind:string,model:string}[]=[];let source='',failedOnce=false,rejectedQuestionOnce=false,currentTask:any,failedExclusionOnce=false;
  const server=createServer(async(req,res)=>{
    let raw='';for await(const c of req)raw+=c;const body=JSON.parse(raw);payloads.push(body);
    const message=[...body.messages].reverse().find((m:any)=>m.role==='user');const text=typeof message.content==='string'?message.content:message.content.map((p:any)=>p.text??'').join('');
    const task=text.includes('Compito (dati):\n')?JSON.parse(text.split('Compito (dati):\n').at(-1)):currentTask;currentTask=task;for(const key of ['task_id','model_key','budget','source_revisions'])assert.equal(Object.hasOwn(task,key),false,'Local checkpoint metadata must stay in the bridge');phases.push(task.kind);trace.push({kind:task.kind,model:body.model});let output:any;
    if(quota&&body.model==='reader'){res.statusCode=400;res.end(JSON.stringify({error:{message:'The ChatGPT user has reached their Subscription Sharing usage limit.',type:'insufficient_quota',code:'quota_exceeded'}}));return;}
    if(resumeExpert&&task.kind==='selection'&&body.model==='test'&&!failedExclusionOnce){failedExclusionOnce=true;res.statusCode=400;res.end(JSON.stringify({error:{message:'Expert interrupted for checkpoint test'}}));return;}
    if(task.kind==='scope')output={summary:'Primo parziale: PRAM',included:['PRAM'],excluded:['Secondo parziale'],clarification:null};
    if(task.kind==='selection')output={decisions:task.previews.map((p:any)=>({source:p.id,status:'relevant',reason:'Contiene PRAM',skills:['PRAM']}))};
    if(['exam_reading','evidence_reading'].includes(task.kind)){
      if(task.kind==='evidence_reading'&&!failedOnce){failedOnce=true;res.statusCode=503;res.end('temporary failure');return;}
      output={evidence:[{concept:'PRAM',statement:'PRAM uses processors and shared memory.',sources:[task.sources[0].id],assumptions:['Abstract model']}],questions:task.kind==='exam_reading'?[{text:'Explain the difference between EREW and CREW. Motivate your answer.',format:'open',in_scope:true,skills:['PRAM'],sources:[task.sources[0].id]}]:[]};
    }
    if(hybrid&&body.model==='reader'&&task.kind==='selection'){output.decisions[0].status='outside';output.decisions[0].reason='Candidate exclusion to verify';}
    if(hybrid&&body.model==='reader'&&task.kind==='evidence_reading'){output.needs_expert=true;output.expert_questions=['Check a notation ambiguity.'];}
    if(task.kind==='exam_reading'&&!rejectedQuestionOnce){rejectedQuestionOnce=true;output.questions[0].text='INVENTED_QUESTION_NOT_IN_PAPER';}
    if(task.kind==='map'||task.kind==='map_outline')output={chapters:[{id:'pram',title:'PRAM dalle basi',objective:'Capire il modello',prerequisites:[],sources:[source],priority:'alta',priority_reason:'Programma e tema autentico',assessment:'Domanda aperta',coverage:[...new Set(task.selection.map((d:any)=>d.document))]}],gaps:[],outside_scope:[],coverage_notes:'Fonti selezionate',objective_coverage:[{index:0,chapters:['pram']}]};
    if(task.kind==='map_contribution')output={additions:[{chapter:'pram',evidence:task.evidence_ids,notes:'Insegna PRAM e gli accessi alla memoria dalle basi.',skills:['PRAM']}]};
    if(task.kind==='map_review')output={summary:'Mappa completa',checked_objectives:[0],issues:[]};
    if(task.kind==='chapter'){assert.deepEqual(task.plan.data.chapters.find((c:any)=>c.$ref),{$ref:'#/chapter'});}
    if(task.kind==='chapter')output={blocks:[{id:'intro',kind:'text',text:'Un algoritmo è una sequenza di istruzioni. PRAM è un modello astratto.',sources:[source]},{id:'worked',kind:'text',text:'Esempio svolto: con due valori serve un livello di riduzione.',sources:[source]},{id:'exercise',kind:'activity',depends_on:['intro'],spec:{kind:'numeric',title:'Variante autonoma',prompt:'Otto valori: quanti livelli?',origin:'generated',assumptions:'Albero binario bilanciato',solution:'Tre livelli',answer:3,rubric:'Numero di livelli',sources:[source],verification:{model:'reduction_depth',input:{n:8},expected:3}}}]};
    if(chunked&&task.kind==='chapter'){
      if(text.includes('Prima restituisci SOLO JSON {outline'))output={outline:[{id:'intro',kind:'text',title:'Foundations',goal:'Explain the model',role:'explain',covers:(task.chapter.exam_skills??[]).map((_:any,i:number)=>i)},{id:'worked',kind:'text',title:'Worked example',goal:'Show reasoning',role:'worked',covers:[]},{id:'exercise',kind:'activity',title:'Transfer',goal:'Apply independently',role:'independent',covers:[]}]};
      else {const pending=JSON.parse(text.match(/Genera SOLO i blocchi richiesti, nello stesso ordine: (.*?)\. Restituisci/)![1]);output={blocks:output.blocks.filter((b:any)=>pending.some((p:any)=>p.id===b.id))};}
    }
    if(task.kind==='review_solve'){
      assert.equal(task.draft.blocks.at(-1).spec.answer,undefined);assert.equal(task.draft.blocks.at(-1).spec.solution,undefined);
      output={solutions:[{block:'exercise',answer:3,reasoning:'Otto valori dimezzati tre volte',sources:[source]}]};
    }
    if(['review_discipline','review_didactic'].includes(task.kind))output={summary:'Revisione completa con fonti originali',checked_blocks:task.draft.blocks.map((b:any)=>b.id),checked_sources:[source],issues:[]};
    res.setHeader('Content-Type','text/event-stream');res.end('data: '+JSON.stringify({id:'selective',object:'chat.completion.chunk',created:1,model:'test',choices:[{index:0,delta:{content:JSON.stringify(output)},finish_reason:'stop'}]})+'\n\ndata: [DONE]\n\n');
  });
  await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));let engine:CourseEngine|undefined;
  try{
    const course='general-course-2026';await bridge.call('import_course',{course});
    const docs=(await bridge.call('course_inventory',{course})).documents;const held=docs.find((d:any)=>d.title==='exam-heldout.pdf').id;
    source=(await bridge.call('search',{course,query:'ordered instructions'}))[0].id;
    const runtime=await ModelRuntime.create({authPath:path.join(root,'auth.json'),modelsPath:null,refreshOnCreate:false});
    runtime.registerProvider('selective-test',{name:'Test',api:'openai-completions',baseUrl:`http://127.0.0.1:${(server.address() as any).port}/v1`,apiKey:'test',models:['test','reader'].map(id=>({id,name:id,reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:64000,maxTokens:8192}))});
    const tutor=new Tutor(bridge,path.join(root,'.state/studio'));tutor.runtime=runtime;
    await bridge.call('setting',{name:'model',value:{provider:'selective-test',id:'test'}});
    if(hybrid)await bridge.call('setting',{name:'preparation_routing',value:{enabled:true,provider:'selective-test',worker:'reader',expert:'test'}});
    engine=new CourseEngine(bridge,tutor);const p=await bridge.call('course_create',{course,request:'Primo parziale: PRAM',reserved:[held]});
    await engine.start(p.id);await idle(engine,p.id);assert.equal((await bridge.call('course_path_view',{path:p.id})).status,'confirm');
    await bridge.call('course_confirm',{path:p.id});await engine.start(p.id);await idle(engine,p.id);
    if(quota){const stopped=await bridge.call('course_path_view',{path:p.id});assert.equal(stopped.status,'error');assert.match(stopped.error,/Subscription Sharing/);assert.equal(trace.filter(t=>t.kind==='selection').length,1);assert.equal(trace.find(t=>t.kind==='selection')?.model,'reader');assert.equal(stopped.profile.total,1);return;}
    if(resumeExpert){
      const interrupted=await bridge.call('course_path_view',{path:p.id});assert.equal(interrupted.status,'error');assert.match(interrupted.error,/Expert interrupted/);
      assert.equal(trace.filter(t=>t.kind==='selection'&&t.model==='reader').length,1);
      await engine.start(p.id);await idle(engine,p.id);
      assert.equal(trace.filter(t=>t.kind==='selection'&&t.model==='reader').length,1,'The completed worker result must survive an expert interruption');
      assert.equal(trace.filter(t=>t.kind==='selection'&&t.model==='test').length,2);
    }
    const ready=await bridge.call('course_path_view',{path:p.id});assert.equal(ready.status,'ready',ready.error);
    assert.equal(ready.profile.total,1);assert.equal(ready.chapters[0].review.status,'reviewed');assert.equal(ready.current.content.blocks.length,3);
    const reconciliationPayload=payloads.find(p=>JSON.stringify(p.messages).includes('reconciliation_version'));assert.ok(reconciliationPayload);assert.ok(!reconciliationPayload.tools?.length);assert.doesNotMatch(JSON.stringify(reconciliationPayload),/create_activity|read_material/);
    assert.ok(phases.includes('map_outline'));assert.ok(phases.includes('map_contribution'));assert.equal(phases.filter(p=>p==='map').length,1);
    const contribution=payloads.find(p=>JSON.stringify(p.messages).includes('evidence_ids'));assert.ok(!contribution.tools?.length);assert.doesNotMatch(JSON.stringify(contribution),/read_ranges|access_fingerprints/);
    if(chunked)assert.equal(phases.filter(p=>p==='chapter').length,3,'Outline and two bounded batches');
    assert.ok(phases.indexOf('exam_reading')<phases.indexOf('selection'));assert.ok(phases.indexOf('review_solve')<phases.indexOf('review_discipline'));assert.ok(phases.indexOf('review_discipline')<phases.indexOf('review_didactic'));
    assert.doesNotMatch(JSON.stringify(payloads),/HOLDOUT_SECRET|HOLDOUT_SOLUTION_SECRET/);
    assert.equal(phases.filter(p=>p==='exam_reading').length,2);
    const diagnostics=JSON.parse(execFileSync(python,['-c',`import sqlite3,json,sys
c=sqlite3.connect(sys.argv[1]);print(json.dumps(c.execute('SELECT error,output FROM prep_rejections').fetchall()))`,path.join(root,'.state/studio/studio.sqlite3')],{encoding:'utf8'}));
    assert.equal(diagnostics.length,1);assert.match(diagnostics[0][0],/questions\[0\]/);assert.match(diagnostics[0][1],/INVENTED_QUESTION_NOT_IN_PAPER/);
    assert.ok(Object.keys(ready.preparation.task_counts).includes('done'));assert.equal(tutor.preparationOwner,undefined);
    if(hybrid){
      for(const kind of ['scope','map_outline','map_contribution','map','map_review','chapter','review_solve','review_discipline','review_didactic'])assert.ok(trace.filter(t=>t.kind===kind).every(t=>t.model==='test'));
      for(const kind of ['selection']){assert.ok(trace.some(t=>t.kind===kind&&t.model==='reader'));assert.ok(trace.some(t=>t.kind===kind&&t.model==='test'));}
      for(const kind of ['exam_reading','evidence_reading'])assert.ok(trace.filter(t=>t.kind===kind).every(t=>t.model==='test'));
      const selectionPayload=payloads.find(p=>p.model==='reader');assert.ok(!selectionPayload.tools?.length);assert.doesNotMatch(JSON.stringify(selectionPayload),/create_activity|LONG_EXAM_TEXT/);
      await bridge.call('setting',{name:'model',value:{provider:'selective-test',id:'reader'}});
      for(const [assessor,role] of [[true,'assessor'],[false,'recall'],[false,'tutor']] as const){const expertSession=await tutor.create(ready.sid,assessor,role);assert.equal(expertSession.model?.id,'test');expertSession.dispose();}
      await bridge.call('setting',{name:'model',value:{provider:'selective-test',id:'test'}});
      const audit=JSON.parse(execFileSync(python,['-c',`import sqlite3,json,sys
c=sqlite3.connect(sys.argv[1]);print(json.dumps(c.execute('SELECT model,data FROM prep_model_calls').fetchall()))`,path.join(root,'.state/studio/studio.sqlite3')],{encoding:'utf8'}));
      assert.ok(audit.some((r:any)=>JSON.parse(r[0]).id==='reader'));assert.ok(audit.some((r:any)=>JSON.parse(r[0]).id==='test'));assert.ok(audit.some((r:any)=>JSON.parse(r[1]).output.includes('INVENTED_QUESTION_NOT_IN_PAPER')));
    }
    const fresh=await bridge.call('preparation_restart',{path:p.id});assert.equal(fresh.plan,null);assert.equal((await bridge.call('preparation_evidence',{path:fresh.id})).length,0);
  }finally{engine?.close();bridge.close();await new Promise<void>(r=>server.close(()=>r()));await rm(root,{recursive:true,force:true});}
}

test('actual Pi selective pipeline reads exams first and publishes only after both full reviews',{skip:!existsSync(python)},()=>selectivePipeline());
test('hybrid Pi uses bounded reader selection, targeted expert exclusions and expert technical reading',{skip:!existsSync(python)},()=>selectivePipeline(true));
test('shared subscription quota stops hybrid preparation without trying to bypass it with another model',{skip:!existsSync(python)},()=>selectivePipeline(true,true));

test('expert interruption resumes the saved worker selection without paying for Luna twice',{skip:!existsSync(python)},()=>selectivePipeline(true,false,true));

test('actual Pi chapter creation checkpoints an outline and batches before the independent reviews',{skip:!existsSync(python)},()=>selectivePipeline(false,false,false,true));

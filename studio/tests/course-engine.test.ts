import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtemp,rm} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import os from 'node:os';
import {existsSync} from 'node:fs';
import {ModelRuntime} from '@earendil-works/pi-coding-agent';
import {Bridge} from '../server/bridge';
import {Tutor} from '../server/tutor';
import {CourseEngine} from '../server/course-engine';
const python=process.env.STUDIO_PYTHON??'/Volumes/ORICO/polimi-lectures/.state/slides-runtime/bin/python';

async function idle(engine:CourseEngine,id:string){const until=Date.now()+20000;while(engine.jobs.has(id)){if(Date.now()>until)throw Error('Worker did not finish');await new Promise(r=>setTimeout(r,20));}}
test('real Pi builds a course in resumable checkpoints without seeing held-out content',{skip:!existsSync(python)},async()=>{
  const root=await mkdtemp(path.join(os.tmpdir(),'studio-course-'));const project=path.resolve(import.meta.dirname,'../..');
  execFileSync(python,['-c',`import sys,pymupdf
from pathlib import Path
p=Path(sys.argv[1])/'corsi'/'general-course-2026'/'materiali';p.mkdir(parents=True)
for name,text in [('lecture.pdf','An algorithm has ordered instructions. PRAM uses processors and shared memory. EREW forbids concurrent reads and writes.'),('exam-training.pdf','Exercise 1. Explain the difference between EREW and CREW. Motivate your answer.'),('exam-heldout.pdf','HOLDOUT_SECRET: explain a fresh algorithm.'),('exam-heldout.sol.pdf','HOLDOUT_SOLUTION_SECRET')]:
 d=pymupdf.open();pg=d.new_page();pg.insert_text((30,40),text);d.save(p/name);d.close()`,root]);
  const bridge=new Bridge(python,project,root);let source='',failed=false,readings=0,searched=false;const requests:any[]=[],documents=new Set<string>();
  const server=createServer(async(req,res)=>{
    let raw='';for await(const c of req)raw+=c;const body=JSON.parse(raw);requests.push(body);
    const user=[...body.messages].reverse().find((m:any)=>m.role==='user');const content=typeof user.content==='string'?user.content:user.content.map((p:any)=>p.text??'').join('');
    const task=content.includes('Compito attuale (dati):\n')?JSON.parse(content.split('Compito attuale (dati):\n').at(-1)):{kind:content.includes('Dati:\n')?'recall':'assess'};
    let output:any;
    const blueprint=(final=false)=>({chapters:[{id:'pram',title:'PRAM dalle basi',objective:'Spiegare processori e accessi',prerequisites:[],sources:[source],priority:'alta',priority_reason:'Programma e domanda aperta nei temi',assessment:'Spiegazione e domanda aperta motivata',coverage:[...documents]}],outside_scope:[],gaps:[],coverage_notes:'Fonti collegate',final});
    if(task.kind==='assess')output={correct:true,feedback:'Risposta corretta secondo le ipotesi dichiarate.',rubric:'Numero di livelli.'};
    if(task.kind==='recall')output={spec:{kind:'numeric',title:'Un problema nuovo',prompt:'Quattro valori con processori sufficienti: quanti livelli servono?',sources:[source],origin:'generated',assumptions:'Somma unitaria',solution:'Due livelli.',rubric:'Numero di livelli',answer:2}};
    if(task.kind==='scope')output={summary:'Primo parziale: PRAM',included:['PRAM'],excluded:['Secondo parziale'],clarification:null};
    if(task.kind==='reading'){
      readings++;
      if(readings===2&&!failed){failed=true;output='invalid-json';}
      else{documents.add(task.document);output={summary:'PRAM e accessi concorrenti',topics:[{title:'PRAM',sources:task.chunks.map((c:any)=>c.source)}],sources:task.chunks.map((c:any)=>c.source),questions:task.exam?[{text:'Explain EREW and CREW',format:'open',in_scope:true,skills:['PRAM'],sources:task.chunks.map((c:any)=>c.source),points:null,depth:'Motivazione'}]:[]};}
    }
    if(task.kind==='integrate'||task.kind==='reconcile')output=blueprint(task.kind==='reconcile');
    if(task.kind==='chapter')output={blocks:[{id:'foundations',kind:'text',text:'Un algoritmo è una sequenza di istruzioni. PRAM è un modello astratto. [Fonte](source:'+source+').',sources:[source]},{id:'worked',kind:'text',text:'Esempio svolto: due processori leggono celle diverse; non vi sono letture concorrenti della stessa cella.',sources:[source]},{id:'independent',kind:'activity',spec:{kind:'open',title:'Una variante autonoma',prompt:'Descrivi quando due letture sono concorrenti.',sources:[source],origin:'generated',assumptions:'PRAM sincrona',solution:'Due processori leggono la stessa cella nello stesso passo.',rubric:'Cellula condivisa e simultaneità'}}]};
    res.setHeader('Content-Type','text/event-stream');const send=(delta:any,finish:any)=>res.write('data: '+JSON.stringify({id:'course',object:'chat.completion.chunk',created:1,model:'test',choices:[{index:0,delta,finish_reason:finish}]})+'\n\n');
    // Exercise actual source tools from a worker before returning a checkpoint.
    if(task.kind==='chapter'&&!searched){searched=true;send({tool_calls:[{index:0,id:'lookup',type:'function',function:{name:'search_sources',arguments:JSON.stringify({query:'PRAM'})}}]},'tool_calls');}
    else send({content:typeof output==='string'?output:JSON.stringify(output)},'stop');
    res.end('data: [DONE]\n\n');
  });
  await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));let engine:CourseEngine|undefined;
  try{
    const course='general-course-2026';await bridge.call('import_course',{course});
    const inventory=await bridge.call('course_inventory',{course});const held=inventory.documents.find((d:any)=>d.title==='exam-heldout.pdf').id;
    source=(await bridge.call('search',{course,query:'ordered instructions'}))[0].id;
    const runtime=await ModelRuntime.create({authPath:path.join(root,'auth.json'),modelsPath:null,refreshOnCreate:false});
    runtime.registerProvider('course-test',{name:'Test',api:'openai-completions',baseUrl:`http://127.0.0.1:${(server.address() as any).port}/v1`,apiKey:'test',models:[{id:'test',name:'Test',reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:64000,maxTokens:4000}]});
    const tutor=new Tutor(bridge,path.join(root,'.state/studio'));tutor.runtime=runtime;
    const p=await bridge.call('course_create',{course,engine:1,request:'Primo parziale: PRAM, dalle basi',reserved:[held]});
    engine=new CourseEngine(bridge,tutor);await engine.start(p.id);await idle(engine,p.id);
    assert.equal((await bridge.call('course_path_view',{path:p.id})).status,'confirm');
    await bridge.call('course_confirm',{path:p.id});await engine.start(p.id);await idle(engine,p.id);
    const interrupted=await bridge.call('course_path_view',{path:p.id});assert.equal(interrupted.status,'error');assert.ok(interrupted.coverage.some((d:any)=>d.done>0));
    engine=new CourseEngine(bridge,tutor);await engine.recover();await engine.start(p.id);await idle(engine,p.id);
    const done=await bridge.call('course_path_view',{path:p.id});assert.equal(done.status,'ready');assert.equal(done.current.content.blocks.length,3);assert.equal(done.profile.formats.open,1);
    assert.equal(done.coverage.filter((d:any)=>!d.excluded).every((d:any)=>d.done===d.total),true);
    assert.equal(done.current.content.blocks.at(-1).spec,undefined);assert.ok(searched);
    assert.doesNotMatch(JSON.stringify(requests),/HOLDOUT_SECRET|HOLDOUT_SOLUTION_SECRET/);
    assert.ok(requests.every(r=>!(r.tools??[]).some((t:any)=>['write','edit','bash','create_activity','revise_course_plan'].includes(t.function?.name))));
    const v=await bridge.call('course_open',{path:p.id});assert.equal(v.activities.length,1);assert.equal(v.activities[0].spec.origin,'generated');assert.equal(v.activities[0].spec.solution,undefined);
    const recalled=await engine.recall(p.id,'pram');const exercise=recalled.activities.at(-1);
    await assert.rejects(()=>tutor.chat(p.sid,'Dammi la soluzione',()=>{}),/Durante il richiamo/);
    const submitted=await bridge.call('event',{sid:p.sid,aid:exercise.id,version:exercise.version,event_id:'recall-answer',kind:'submit',payload:{answer:2}});
    await tutor.assess(p.sid,submitted.attempt.id);
    const cards=await bridge.call('course_recalls',{path:p.id});assert.equal(cards.length,1);assert.ok(cards[0].card.due);assert.equal(cards[0].card.provisional,true);
    const progress=(await bridge.call('view',{sid:p.sid})).progress;
    assert.ok(!progress.some((c:any)=>c.status==='riconfermato a distanza'));
    const after=await bridge.call('course_path_view',{path:p.id});assert.equal(after.recall,null);
  }finally{engine?.close();bridge.close();await new Promise<void>(r=>server.close(()=>r()));await rm(root,{recursive:true,force:true});}
});

test('reading card repair handles size, summary and citations once without committing invalid data',async()=>{
  for(const failure of ['citation','oversized','missing'])for(const staysInvalid of [false,true]){
    let committed=false,requests=0;const prompts:string[]=[],statuses:string[]=[];
    const bridge={call:async(method:string,args:any)=>{
      if(method==='course_path_view')return {sid:'session',position:{chapter:'chapter'},chapters:[]};
      if(method==='course_status'){statuses.push(args.status);return {};}
      if(method==='course_task')return committed?{kind:'done'}:{kind:'reading',allowed_sources:['read:0'],chunks:[{source:'read:0'}],previous:{}};
      if(method==='course_commit'){
        if(!args.result.summary?.trim())throw Error('Scheda fonte senza sintesi: compila summary con una sintesi non vuota.');
        if(args.result.summary.length>16000)throw Error('Scheda fonte troppo lunga: 17000 caratteri; limite 16000.');
        if(args.result.sources[0]!=='read:0')throw Error('La scheda deve citare i passaggi effettivamente letti.');
        committed=true;return {};
      }
      throw Error('Unexpected method '+method);
    }} as unknown as Bridge;
    let listener:(event:any)=>void=()=>{};
    const tutor={create:async()=>({subscribe:(fn:any)=>{listener=fn;return ()=>{};},dispose:()=>{},abort:async()=>{},prompt:async(prompt:string)=>{
      prompts.push(prompt);requests++;
      const invalid=requests===1||staysInvalid;
      listener({type:'message_update',assistantMessageEvent:{type:'text_delta',delta:JSON.stringify({summary:invalid&&failure==='missing'?'':invalid&&failure==='oversized'?'x'.repeat(17000):'A source-grounded card',sources:[invalid&&failure==='citation'?'unread:0':'read:0']})}});
    }})} as unknown as Tutor;
    const engine=new CourseEngine(bridge,tutor);
    await engine.start('path');await idle(engine,'path');
    assert.equal(requests,2);assert.match(prompts[1],/non è stato salvato/);assert.match(prompts[1],/read:0/);
    assert.equal(committed,!staysInvalid);assert.equal(statuses.at(-1),staysInvalid?'error':'ready');
  }
});

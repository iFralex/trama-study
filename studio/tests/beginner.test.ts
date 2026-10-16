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

const python=process.env.STUDIO_PYTHON??'/Volumes/ORICO/polimi-lectures/.state/slides-runtime/bin/python';
test('beginner journey uses real source bridge and Pi tools before explaining from zero',{skip:!existsSync(python)},async()=>{
  const root=await mkdtemp(path.join(os.tmpdir(),'studio-beginner-'));
  const project=path.resolve(import.meta.dirname,'../..');
  execFileSync(python,['-c',`import sys,json,pymupdf
from pathlib import Path
root=Path(sys.argv[1]);course=root/'corsi'/'test-course-2026'
materials=course/'materiali';materials.mkdir(parents=True)
doc=pymupdf.open();p=doc.new_page();p.insert_text((30,40),'An algorithm is a sequence of steps. A processor executes instructions. Parallel execution uses several processors.');doc.save(materials/'lecture1.pdf');doc.close()
transcript=course/'2026-09-01_lesson1'/'trascrizione';transcript.mkdir(parents=True)
(transcript/'trascrizione.json').write_text(json.dumps({'segments':[{'start':10,'end':30,'text':'First define an algorithm: a sequence of steps. Then define a processor before parallel execution.'}]}))
(transcript/'completa.json').write_text('{}')`,root],{cwd:project});
  const bridge=new Bridge(python,project,root);
  const requests:any[]=[];let step=0,source='',lesson='';
  const server=createServer(async(req,res)=>{
    let text='';for await(const chunk of req)text+=chunk;const body=JSON.parse(text);requests.push(body);
    res.setHeader('Content-Type','text/event-stream');
    const send=(delta:any,finish:any)=>res.write('data: '+JSON.stringify({id:'beginner',object:'chat.completion.chunk',created:1,model:'test',choices:[{index:0,delta,finish_reason:finish}]})+'\n\n');
    const actions=[
      ['read_lesson',{}],['read_source',{id:source}],
      ['set_lesson_plan',{lesson,units:[{title:'Algoritmi e processori',objective:'Capire cosa esegue un processore, prima del parallelismo.',prerequisites:[],sources:[source]}]}],
      ['create_activity',{spec:{kind:'explain',title:'Che cosa significa eseguire un algoritmo?',prompt:'Un algoritmo è una sequenza di passi. Come una ricetta, ogni passo prepara il successivo. Un processore esegue istruzioni: partiamo da qui prima di usare più processori.',concept:'intro',sources:[source]}}],
    ];
    if(step<actions.length){const [name,args]=actions[step++];send({tool_calls:[{index:0,id:'tool'+step,type:'function',function:{name,arguments:JSON.stringify(args)}}]},'tool_calls');}
    else send({content:'Partiamo dalle basi: un algoritmo è una sequenza di passi; un processore esegue istruzioni. [Lezione](source:'+source+').'},'stop');
    res.end('data: [DONE]\n\n');
  });
  await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));
  try{
    await bridge.call('import_course',{course:'test-course-2026'});
    const view=await bridge.call('open_session',{course:'test-course-2026',fresh:true,approach:'beginner'});const sid=view.session.id;
    assert.equal(view.activities.length,0);lesson=view.learning.lesson.id;
    source=(await bridge.call('lesson_bundle',{sid})).passages[0].id;
    const runtime=await ModelRuntime.create({authPath:path.join(root,'auth.json'),modelsPath:null,refreshOnCreate:false});
    runtime.registerProvider('beginner-test',{name:'Test',api:'openai-completions',baseUrl:`http://127.0.0.1:${(server.address() as any).port}/v1`,apiKey:'test',models:[{id:'test',name:'Test',reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:64000,maxTokens:4000}]});
    const tutor=new Tutor(bridge,path.join(root,'.state/studio'));tutor.runtime=runtime;
    let output='';await tutor.chat(sid,'Parti da zero seguendo la mia lezione.',delta=>output+=delta);
    const after=await bridge.call('view',{sid});assert.equal(after.learning.phase,'foundations');assert.equal(after.learning.current_unit.sources[0],source);
    assert.equal(after.activities[0].spec.beginner.phase,'foundations');assert.equal(after.activities[0].spec.grading_origin,'generated');assert.match(output,/sequenza di passi/);
    assert.match(JSON.stringify(requests[0].messages),/First define an algorithm/);assert.match(JSON.stringify(requests[0].messages),/non conosca ancora l'argomento/);
    await bridge.call('advance_beginner',{sid});await tutor.chat(sid,'Continua dalla fase corrente.',()=>{});
    const contents=requests.at(-1).messages.map((m:any)=>typeof m.content==='string'?m.content:(m.content??[]).map((p:any)=>p.text??'').join(' ')).join('\n');
    assert.ok(contents.includes('"phase":"explain"'));
  }finally{bridge.close();await new Promise<void>(r=>server.close(()=>r()));await rm(root,{recursive:true,force:true});}
});

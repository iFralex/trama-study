import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {ModelRuntime} from '@earendil-works/pi-coding-agent';
import {Tutor} from '../server/tutor';
import type {Bridge} from '../server/bridge';
import {expandSources} from './helpers/model-payload';

test('real SDK review can save an isolated assessment and journal evidence; explanation cannot repeat either',async()=>{
  const root=await mkdtemp(path.join(os.tmpdir(),'attempt-review-sdk-'));
  const requests:any[]=[],calls:string[]=[],messages:any[]=[];let step=0;
  let grade:any={status:'provisional',correct:null,feedback:'Risposta salvata.'};
  const sourceText='Ogni processore ha registri privati. '.repeat(50);
  const sources=[{id:'source',document:'doc',page:1,text:sourceText,context:[{id:'adjacent',page:2,text:sourceText}]},{id:'adjacent',document:'doc',page:2,text:sourceText,context:[{id:'source',page:1,text:sourceText}]}];
  const activity={id:'exercise',version:1,spec:{kind:'open',prompt:'Di chi sono i registri PRAM?',rubric:'Natura privata.',sources:['source'],curriculum:{chapter:'pram'}}};
  const context={session:{id:'session',course:'course',mode:'learn'},curriculum:{path:'path',chapter:'pram',history:'HISTORY_DO_NOT_SEND'.repeat(10000)},activities:[activity],attempts:[]};
  const bridge={async call(method:string,args:any={}){
    calls.push(method);
    if(method==='setting')return null;
    if(method==='view'||method==='context')return context;
    if(method==='assessment')return {attempt:{id:'attempt',answer:'Appartengono al singolo processore.',grade},activity,sources};
    if(method==='assess'){grade={...args.grade,status:'provisional',previous:grade};return grade;}
    if(method==='course_note')return {id:'note'};
    if(method==='course_recall_card')return {duplicate:true};
    if(method==='message'){messages.push(args);return 'message';}
    throw Error('Unexpected bridge method: '+method);
  }} as unknown as Bridge;
  const server=createServer(async(req,res)=>{
    let text='';for await(const chunk of req)text+=chunk;
    const body=JSON.parse(text);requests.push(body);
    const names=body.tools?.map((t:any)=>t.function.name)??[];
    res.setHeader('Content-Type','text/event-stream');
    const push=(delta:any,finish:any=null)=>res.write('data: '+JSON.stringify({id:'reply',object:'chat.completion.chunk',created:1,model:'review-model',choices:[{index:0,delta,finish_reason:finish}]})+'\n\n');
    if(!names.length){push({content:JSON.stringify({correct:true,feedback:'Corretto: i registri sono privati.',rubric:'Natura privata.'})});push({},'stop');}
    else if(names.includes('assess_study_attempt')&&step===0){
      step++;push({role:'assistant',tool_calls:[{index:0,id:'assess',type:'function',function:{name:'assess_study_attempt',arguments:'{"attempt_id":"attempt"}'}}]});push({},'tool_calls');
    }else if(names.includes('record_study_note')&&step===1){
      step++;push({role:'assistant',tool_calls:[{index:0,id:'note',type:'function',function:{name:'record_study_note',arguments:JSON.stringify({kind:'hypothesis',text:'Ha distinto i registri privati.',evidence:['attempt']})}}]});push({},'tool_calls');
    }else{push({content:'Spiegazione estesa: gli altri processori non accedono direttamente ai registri.'});push({},'stop');}
    res.end('data: [DONE]\n\n');
  });
  await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
  try{
    const runtime=await ModelRuntime.create({authPath:path.join(root,'auth.json'),modelsPath:null,modelsStorePath:path.join(root,'models.json'),refreshOnCreate:false});
    runtime.registerProvider('review-test',{name:'Review test',api:'openai-completions',baseUrl:`http://127.0.0.1:${(server.address() as any).port}/v1`,apiKey:'test-only',models:[{id:'review-model',name:'Review',reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:32000,maxTokens:4000}]});
    const tutor=new Tutor(bridge,root);tutor.runtime=runtime;
    let output='';await tutor.chat('session','Valuta e registra le evidenze.',delta=>output+=delta,true,'attempt');
    const tools=requests[0].tools.map((t:any)=>t.function.name);
    assert.ok(tools.includes('assess_study_attempt'),'review role must expose assessment');
    assert.ok(tools.includes('record_study_note'),'review role must expose evidence recording');
    assert.equal(calls.filter(c=>c==='assess').length,1);assert.equal(calls.filter(c=>c==='course_note').length,1);
    assert.equal(grade.correct,true);assert.ok(grade.previous);assert.match(output,/Spiegazione estesa/);
    assert.ok(messages.some(m=>m.role==='assistant'&&m.text===output));
    assert.doesNotMatch(JSON.stringify(requests[0].messages),/HISTORY_DO_NOT_SEND/);
    await tutor.chat('session','Analizza il tentativo: usa assess_study_attempt e registra evidenze.',()=>{},true,'attempt');
    assert.equal(calls.filter(c=>c==='assess').length,1);assert.equal(calls.filter(c=>c==='course_note').length,1);
    assert.doesNotMatch(JSON.stringify(requests.at(-1).messages.at(-1)),/usa assess_study_attempt/);
    const explanationTools=requests.at(-1).tools.map((t:any)=>t.function.name);
    assert.ok(!explanationTools.includes('assess_study_attempt'));assert.ok(!explanationTools.includes('record_study_note'));
    // The default submit path now calls the isolated grader directly, without an agent turn.
    grade={status:'provisional',correct:null,feedback:'Risposta salvata.'};
    const before=requests.length,notesBefore=calls.filter(c=>c==='course_note').length,messagesBefore=messages.length;
    const compact=await tutor.assess('session','attempt');
    assert.equal(compact.correct,true);assert.equal(requests.length,before+1);
    assert.equal(requests.at(-1).tools?.length??0,0);
    const content=requests.at(-1).messages.at(-1).content;
    const packet=JSON.parse(typeof content==='string'?content:content.map((p:any)=>p.text??'').join(''));
    assert.ok(packet._source_texts);assert.deepEqual(expandSources(packet).sources,sources);
    assert.equal(calls.filter(c=>c==='course_note').length,notesBefore);assert.equal(messages.length,messagesBefore);
    assert.equal(tutor.active.size,0);assert.equal(tutor.busySessions.size,0);
    await tutor.assess('session','attempt');assert.equal(requests.length,before+1,'saved assessments must not spend another model call');

  }finally{await new Promise<void>(resolve=>server.close(()=>resolve()));await rm(root,{recursive:true,force:true});}
});

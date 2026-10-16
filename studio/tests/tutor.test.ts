import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {ModelRuntime} from '@earendil-works/pi-coding-agent';
import {Tutor} from '../server/tutor';
import type {Bridge} from '../server/bridge';

test('actual Pi SDK streams, calls study tools, sees interactions and assesses separately',async()=>{
  const root=await mkdtemp(path.join(os.tmpdir(),'pi-study-test-'));
  const requests:any[]=[],calls:any[]=[],messages:any[]=[];
  let toolStep=0,unavailable=false;
  const server=createServer(async(req,res)=>{
    let text='';for await(const chunk of req)text+=chunk;
    const body=JSON.parse(text);requests.push(body);
    if(unavailable){res.statusCode=400;res.setHeader('Content-Type','application/json');res.end(JSON.stringify({error:{message:'test provider unavailable',type:'invalid_request_error'}}));return;}
    res.setHeader('Content-Type','text/event-stream');
    const push=(delta:any,finish_reason:any=null)=>res.write('data: '+JSON.stringify({id:'reply',object:'chat.completion.chunk',created:1,model:'test-model',choices:[{index:0,delta,finish_reason}]})+'\n\n');
    if(!body.tools?.length){push({content:JSON.stringify({correct:true,feedback:'Coerente con la fonte, verifica le ipotesi.',rubric:'Letture e scritture'})});push({},'stop');}
    else if(toolStep++===0){push({role:'assistant',tool_calls:[{index:0,id:'search1',type:'function',function:{name:'search_sources',arguments:'{"query":"PRAM"}'}}]});push({},'tool_calls');}
    else if(toolStep===2){push({role:'assistant',tool_calls:[{index:0,id:'activity1',type:'function',function:{name:'create_activity',arguments:JSON.stringify({spec:{kind:'html',title:'Prova',prompt:'Modifica il numero.',concept:'pram',sources:['source1'],html:'<input data-key="processors" value="4">',fallback:'Quattro processori.'}})}}]});push({},'tool_calls');}
    else{push({content:'**PRAM**: osserviamo il caso. [Fonte](source:source1)'});push({},'stop');}
    res.end('data: [DONE]\n\n');
  });
  await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
  const address=server.address() as any;
  const context={session:{id:'study',course:'course',mode:'learn'},progress:[],activity:null,interactions:[{kind:'try',payload:{processors:4}}],attempts:[{id:'attempt1',activity:'a',version:1,answer:'CREW',grade:{status:'provisional'}}]};
  const bridge={async call(method:string,args:any={}){calls.push({method,args});
    if(method==='setting')return null;
    if(method==='context')return context;
    if(method==='message'){messages.push(args);return 'm';}
    if(method==='search')return [{id:'source1',course:'course',text:'CREW concurrent reads, exclusive writes.',quality:'originale'}];
    if(method==='source')return {id:'source1',course:'course',text:'CREW concurrent reads, exclusive writes.'};
    if(method==='activity')return {spec:{prompt:'Define CREW',rubric:'Letture/scritture',sources:['source1']}};
    if(method==='assessment')return {attempt:{answer:'CREW'},activity:{spec:{prompt:'Define CREW',rubric:'Letture/scritture'}},sources:[{id:'source1',text:'CREW concurrent reads, exclusive writes.',solution:1}]};
    if(method==='create_activity')return {id:'a',version:1};
    if(method==='assess')return {...args.grade,status:'provisional'};
    throw Error('Unexpected method '+method);
  }} as unknown as Bridge;
  try{
    const runtime=await ModelRuntime.create({authPath:path.join(root,'auth.json'),modelsPath:null,modelsStorePath:path.join(root,'models.json'),refreshOnCreate:false});
    runtime.registerProvider('study-test',{name:'Test only',api:'openai-completions',baseUrl:`http://127.0.0.1:${address.port}/v1`,apiKey:'test-only',models:[{id:'test-model',name:'Test',reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:32000,maxTokens:4000}]});
    const tutor=new Tutor(bridge,root);tutor.runtime=runtime;
    let output='';await tutor.chat('study','Spiega e fammi provare.',delta=>output+=delta);
    assert.match(output,/PRAM/);assert.ok(calls.some(c=>c.method==='search'));assert.ok(calls.some(c=>c.method==='create_activity'));
    const contextText=JSON.stringify(requests[0].messages);assert.match(contextText,/processors/);
    assert.deepEqual(requests[0].tools.map((t:any)=>t.function.name).sort(),['create_activity','get_context','read_source','search_sources']);
    assert.ok(messages.some(m=>m.role==='user'));assert.ok(messages.some(m=>m.role==='assistant'));
    const grade=await tutor.assess('study','attempt1');assert.equal(grade.status,'provisional');assert.equal(requests.at(-1).tools?.length??0,0);
    const before=requests.length;context.session.mode='exam';await assert.rejects(()=>tutor.chat('study','Give answers',()=>{}),/simulazione/);assert.equal(requests.length,before);
    context.session.mode='learn';unavailable=true;
    await assert.rejects(()=>tutor.chat('study','Questa risposta deve restare salvata.',()=>{}),/provider unavailable/);
    assert.ok(messages.some(m=>m.text==='Questa risposta deve restare salvata.'&&m.role==='user'));
  }finally{await new Promise<void>(resolve=>server.close(()=>resolve()));await rm(root,{recursive:true,force:true});}
});

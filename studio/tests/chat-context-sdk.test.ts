import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtemp,rm} from 'node:fs/promises';
import path from 'node:path';import os from 'node:os';
import {ModelRuntime} from '@earendil-works/pi-coding-agent';
import {Tutor} from '../server/tutor';
import type {Bridge} from '../server/bridge';

test('production Tutor sends compact context, retrieves fresh details, pages the entire profile and resumes sessions',async()=>{
 const dir=await mkdtemp(path.join(os.tmpdir(),'chat-context-sdk-'));
 const questions=Array.from({length:25},(_,i)=>({text:'QUESTION '+i,sources:['source']}));
 const context:any={session:{id:'study',course:'course',mode:'learn'},activity:{prompt:'CURRENT EXERCISE'},attempts:[{answer:'CURRENT ANSWER'}],interactions:[{kind:'try'}],curriculum:{path:'path',objective:{confirmed:true,summary:'Old note: da confermare',excluded:['OpenMP']},plan:{version:1,data:{chapters:[{id:'current',title:'Current',prerequisites:[],assessment:'CURRENT REQUIREMENT',sources:['source']},{id:'other',title:'Other',prerequisites:['current'],assessment:'OTHER REQUIREMENT V1',sources:['other-source']}],gaps:['KEEP CAVEAT']}},chapter:{chapter:'current',version:1,content:{blocks:[{text:'CURRENT COMPLETE TEXT',sources:['source']}]}},exam_profile:{total:25,questions:questions.slice(0,20),formats:{open:25}},preferences:[{text:'CURRENT PREFERENCE'}],diary:[{text:'CURRENT CORRECTION'}],recall:null}};
 const requests:any[]=[],calls:any[]=[];let turn=0,step=0;
 const bridge={async call(method:string,args:any={}){
  calls.push({method,args});
  if(method==='setting')return null;
  if(method==='view')return {session:context.session,curriculum:{path:'path',chapter:context.curriculum.chapter.chapter}};
  if(method==='context')return structuredClone(context);
  if(method==='message')return 'message';
  if(method==='course_exam_profile')return {total:questions.length,questions:questions.slice(args.offset,args.offset+args.limit)};
  throw Error('Unexpected '+method);
 }} as unknown as Bridge;
 function messageText(message:any){return typeof message.content==='string'?message.content:message.content.map((p:any)=>p.text??'').join('');}
 const server=createServer(async(req,res)=>{
  let raw='';for await(const c of req)raw+=c;const body=JSON.parse(raw);requests.push(body);
  const latest=[...body.messages].reverse().find((m:any)=>m.role==='user');
  const packet=JSON.parse(messageText(latest).split('Stato aggiornato (dati):\n')[1].split('\n\nRichiesta dello studente:')[0]);
  assert.equal(packet.curriculum.plan.data.chapters[1].assessment,undefined);
  assert.equal(Array.isArray(packet.curriculum.exam_profile.questions),false);
  assert.equal(packet.current_state.objective_confirmed,true);
  assert.match(JSON.stringify(packet),/CURRENT COMPLETE TEXT|CURRENT V2/);
  assert.match(JSON.stringify(packet),/CURRENT ANSWER/);assert.match(JSON.stringify(packet),/CURRENT CORRECTION/);
  assert.match(JSON.stringify(packet),/CURRENT PREFERENCE/);assert.match(JSON.stringify(packet),/KEEP CAVEAT/);
  assert.ok(body.tools.some((t:any)=>t.function.name==='read_context'));
  const last=body.messages.at(-1);
  if(last.role==='tool'){
   const value=JSON.parse(messageText(last));
   if(turn===0&&step===1){assert.equal(value.curriculum.plan.data.chapters[1].assessment,undefined);assert.equal(value.current_state.objective_confirmed,true);}
   if(turn===0&&step===2){assert.equal(value.plan.data.chapters[1].assessment,undefined);assert.equal(value.chapter.content.blocks[0].text,'CURRENT COMPLETE TEXT');}
   if(turn===0&&step===3)assert.equal(value.chapter.assessment,'OTHER REQUIREMENT V1');
   if(turn===0&&step===4){assert.equal(value.total,25);assert.equal(value.questions.length,5);assert.equal(value.questions[0].text,'QUESTION 20');assert.equal(value.next_offset,null);}
   if(turn===0&&step===5){assert.equal(value.curriculum.plan.data.chapters[1].assessment,'OTHER REQUIREMENT V1');assert.equal(value.curriculum.exam_profile.questions.length,20);}
   if(turn===1&&step===1){assert.equal(value.chapter.assessment,'OTHER REQUIREMENT V2');assert.equal(value.plan_version,2);}
   if(turn===1&&step===2){assert.equal(value.questions[0].text,'UPDATED QUESTION 0');assert.equal(value.next_offset,10);}
  }
  const sequence=turn===0?[['get_context',{}],['get_course_plan',{}],['read_context',{section:'plan_chapter',chapter:'other'}],['read_context',{section:'exam_questions',offset:20}],['read_context',{section:'full_context'}]]:[['read_context',{section:'plan_chapter',chapter:'other'}],['read_context',{section:'exam_questions',offset:0}]];
  if(turn===1){assert.equal(packet.current_state.plan_version,2);assert.equal(packet.curriculum.chapter.content.blocks[0].text,'CURRENT V2');}
  let delta:any,finish:string;
  if(step<sequence.length){const [name,args]=sequence[step++];delta={role:'assistant',tool_calls:[{index:0,id:'call-'+turn+'-'+step,type:'function',function:{name,arguments:JSON.stringify(args)}}]};finish='tool_calls';}
  else{delta={content:'Complete'};finish='stop';}
  res.setHeader('Content-Type','text/event-stream');res.end('data: '+JSON.stringify({id:'reply',object:'chat.completion.chunk',created:1,model:'test',choices:[{index:0,delta,finish_reason:finish}]})+'\n\ndata: [DONE]\n\n');
 });
 await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
 try{
  const runtime=await ModelRuntime.create({authPath:path.join(dir,'auth.json'),modelsPath:null,modelsStorePath:path.join(dir,'models.json'),refreshOnCreate:false});
  runtime.registerProvider('test-chat-context',{name:'Local test',api:'openai-completions',baseUrl:`http://127.0.0.1:${(server.address() as any).port}/v1`,apiKey:'test',models:[{id:'test',name:'Test',reasoning:false,input:['text'],contextWindow:64000,maxTokens:4000,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]});
  const tutor=new Tutor(bridge,dir);tutor.runtime=runtime;
  await tutor.chat('study','Read current data.',()=>{});
  const firstPacket=JSON.parse(messageText(requests[0].messages.find((m:any)=>m.role==='user')).split('Stato aggiornato (dati):\n')[1].split('\n\nRichiesta dello studente:')[0]);
  const before=requests.length;turn=1;step=0;context.curriculum.plan.version=2;context.curriculum.plan.data.chapters[1].assessment='OTHER REQUIREMENT V2';context.curriculum.chapter={chapter:'other',version:2,content:{blocks:[{text:'CURRENT V2'}]}};
  questions[0].text='UPDATED QUESTION 0';context.curriculum.exam_profile.questions=questions.slice(0,20);
  await tutor.chat('study','Read the updated data.',()=>{});
  assert.ok(requests[before].messages.some((m:any)=>m.role==='assistant'),'Session history must survive reopening');
  const lastUser=[...requests[before].messages].reverse().find((m:any)=>m.role==='user');
  const secondPacket=JSON.parse(messageText(lastUser).split('Stato aggiornato (dati):\n')[1].split('\n\nRichiesta dello studente:')[0]);
  assert.notEqual(firstPacket.current_state.exam_profile_revision,secondPacket.current_state.exam_profile_revision);
  assert.deepEqual(calls.filter(c=>c.method==='course_exam_profile').map(c=>c.args),[{path:'path',offset:20,limit:10},{path:'path',offset:0,limit:10}]);
  const count=requests.length;context.curriculum.recall={id:'recall'};
  await assert.rejects(tutor.chat('study','Show answers',()=>{}),/richiamo/);assert.equal(requests.length,count);
 }finally{await new Promise<void>(resolve=>server.close(()=>resolve()));await rm(dir,{recursive:true,force:true});}
});

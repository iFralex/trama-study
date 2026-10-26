import test from 'node:test';
import assert from 'node:assert/strict';
import {reviewChecklist,reviewRepairPrompt} from '../server/preparation-review';
import {runPreparation} from '../server/preparation-engine';
import type {Bridge} from '../server/bridge';
import type {Tutor} from '../server/tutor';

const task={kind:'review_discipline',chapter:{id:'chapter'},draft_revision:2,originals:[{id:'supplied',text:'Original text'}],draft:{blocks:[{id:'intro',kind:'text',text:'Already reviewed text.',sources:['supplied']},{id:'exercise',kind:'activity',spec:{sources:['tool-read'],prompt:'Exercise'}},{id:'extra',kind:'text',text:'A claim with an additional citation.',sources:['supplied']}]}};

test('review checklist distinguishes all required references from originals already provided',()=>{
  assert.deepEqual(reviewChecklist(task),{required_blocks:['intro','exercise','extra'],required_sources:['supplied','tool-read'],sources_in_input:['supplied'],sources_to_retrieve:['tool-read']});
  assert.equal(reviewChecklist({kind:'chapter'}),null);
});

test('targeted repair preserves the rejected review and includes only blocks requiring missing evidence',()=>{
  const previous={summary:'Complete review',checked_sources:['supplied','tool-read','unread'],checked_blocks:['intro','exercise','extra'],issues:[{block:'extra',severity:'warning',message:'Check the additional citation.',sources:['unread']}]};
  const prompt=reviewRepairPrompt(task,previous,'Citazione non letta: unread',['supplied','tool-read']);
  const data=JSON.parse(prompt.split('Dati della riparazione:\n')[1]);
  assert.deepEqual(data.previous_review,previous);assert.deepEqual(data.attention_sources,['unread']);
  assert.deepEqual(data.blocks_to_recheck.map((b:any)=>b.id),['extra']);assert.doesNotMatch(prompt,/Already reviewed text/);
  assert.match(prompt,/non inventare letture/);assert.match(prompt,/JSON COMPLETO/);
});

test('repair of an incomplete bibliography retains sources from the original input in its checklist',()=>{
  const previous={summary:'Partial inventory',checked_sources:['tool-read'],checked_blocks:['intro','exercise','extra'],issues:[]};
  const data=JSON.parse(reviewRepairPrompt(task,previous,'Missing supplied',['supplied','tool-read']).split('Dati della riparazione:\n')[1]);
  assert.deepEqual(data.attention_sources,['supplied']);assert.deepEqual(data.blocks_to_recheck.map((b:any)=>b.id),['intro','extra']);
  assert.deepEqual(data.checklist.sources_in_input,['supplied']);
});

async function resumeReview(valid=false,reject=false){
  const previous={summary:'Prior review',checked_blocks:['intro','exercise','extra'],checked_sources:['supplied','tool-read','unread'],issues:[{block:'extra',severity:'warning',message:'Verify the additional reference.',sources:['unread']}]};
  let complete=false,asks=0;const prompts:string[]=[],states:string[]=[];
  const bridge={async call(method:string,args:any={}){
    if(method==='course_path_view')return {sid:'session',status:'error'};
    if(method==='course_status'){states.push(args.status);return {};}
    if(method==='course_peek_task')return complete?{kind:'done'}:task;
    if(method==='course_task')return {...task,task_id:'task'};
    if(method==='preparation_begin')return {metrics:{},review_recovery:{result:previous,error:valid?'':'Citazione non letta: unread',read_sources:['supplied','tool-read']}};
    if(method==='preparation_commit'){if(reject)throw Error('La revisione deve verificare le fonti dei blocchi.');complete=true;return {};}
    if(['preparation_metric','preparation_model_call','preparation_usage','preparation_reject'].includes(method))return {};
    throw Error(method);
  }} as unknown as Bridge;
  let emit=(event:any)=>{};
  const tutor={busySessions:new Set(),preparationOwner:undefined,async preparationRouting(){return null;},async preparationBudget(){return {input:32000,context:64000,output:8192,key:'test:model',model:{provider:'test',id:'model'}};},async create(){return {subscribe(callback:any){emit=callback;return()=>{};},async prompt(text:string){asks++;prompts.push(text);emit({type:'message_update',assistantMessageEvent:{type:'text_delta',delta:JSON.stringify(previous)}});},dispose(){}};}} as unknown as Tutor;
  const work=runPreparation(bridge,tutor,'path',{paused:false});
  if(reject)await assert.rejects(work,/fonti dei blocchi/);else await work;
  return {asks,prompts,states,tutor};
}

test('resuming a rejected review asks only for targeted repair and does not repeat the full review',async()=>{
  const result=await resumeReview();assert.equal(result.asks,1);assert.deepEqual(result.states,['running','ready']);
  assert.match(result.prompts[0],/previous_review/);assert.doesNotMatch(result.prompts[0],/Already reviewed text/);
  assert.equal(result.tutor.preparationOwner,undefined);
});

test('an already valid recovered review commits without another model request',async()=>{
  const result=await resumeReview(true);assert.equal(result.asks,0);assert.deepEqual(result.states,['running','ready']);
});

test('a failed resumed repair stops after one request without bypassing validation',async()=>{
  const result=await resumeReview(false,true);assert.equal(result.asks,1);assert.equal(result.tutor.preparationOwner,undefined);
});

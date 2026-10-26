import test from 'node:test';
import assert from 'node:assert/strict';
import {Tutor} from '../server/tutor';
import type {Bridge} from '../server/bridge';

function harness(graded=false){
  const roles:string[]=[],prompts:string[]=[],calls:string[]=[];
  const context={session:{id:'study',course:'course',mode:'learn'},curriculum:{path:'path',history:'irrelevant-history'.repeat(30000)}};
  const assessment={attempt:{id:'attempt',answer:'I registri sono privati.',grade:graded?{correct:false,feedback:'Manca il costo unitario.',previous:{}}:{correct:null}},activity:{id:'activity',version:1,spec:{kind:'open',prompt:'Descrivi i registri PRAM.',sources:['source']}}};
  const bridge={async call(method:string,args:any){calls.push(method);if(method==='context')return context;if(method==='assessment'){assert.equal(args.attempt_id,'attempt');return assessment;}if(method==='message')return 'message';throw Error(method);}} as unknown as Bridge;
  const tutor=new Tutor(bridge,'/private/tmp/attempt-review-test');
  let listener=(event:any)=>{},finish:()=>void=()=>{},aborted=0;
  tutor.create=(async(_sid:string,_assessor:boolean,role:string)=>{roles.push(role);return {subscribe(cb:any){listener=cb;return()=>{};},async prompt(text:string){prompts.push(text);listener({type:'message_end',message:{role:'assistant',stopReason:'stop'}});},async abort(){aborted++;finish();},dispose(){}};}) as any;
  return {tutor,roles,prompts,calls,emit:(event:any)=>listener(event),setFinish:(fn:()=>void)=>{finish=fn;},get aborted(){return aborted;}};
}

test('automatic review uses a fresh role and only the submitted exercise, answer and source references',async()=>{
  const h=harness();await h.tutor.chat('study','Correggi il tentativo.',()=>{},true,'attempt');
  assert.deepEqual(h.roles,['attempt_review']);assert.ok(h.prompts[0].length<2000);
  assert.match(h.prompts[0],/I registri sono privati/);assert.match(h.prompts[0],/source/);
  assert.doesNotMatch(h.prompts[0],/irrelevant-history/);assert.equal(h.calls.includes('assess'),false);
});

test('resuming a saved assessment selects the explanation role and supplies the saved grade',async()=>{
  const h=harness(true);await h.tutor.chat('study','Completa la spiegazione.',()=>{},true,'attempt');
  assert.deepEqual(h.roles,['review_explanation']);assert.match(h.prompts[0],/senza rivalutare/);assert.match(h.prompts[0],/Manca il costo unitario/);
});

test('a recovered provider retry does not leave an earlier stream error as the final result',async()=>{
  const h=harness();h.tutor.create=(async()=>({subscribe(cb:any){h.emit=cb;return()=>{};},async prompt(){h.emit({type:'message_end',message:{role:'assistant',stopReason:'error',errorMessage:'stream interrupted'}});h.emit({type:'message_end',message:{role:'assistant',stopReason:'stop'}});},async abort(){},dispose(){}})) as any;
  await h.tutor.chat('study','Domanda.',()=>{});assert.equal(h.tutor.busySessions.size,0);
});

test('the local deadline reports a timeout rather than a misleading provider stream error',async()=>{
  const h=harness(true);h.tutor.turnTimeoutMs=5;
  h.tutor.create=(async()=>({subscribe(cb:any){h.emit=cb;return()=>{};},prompt(){return new Promise<void>(resolve=>h.setFinish(resolve));},async abort(){h.emit({type:'message_end',message:{role:'assistant',stopReason:'aborted',errorMessage:'OpenAI Responses stream ended before a terminal response event'}});finish();},dispose(){}})) as any;
  let finish=()=>{};
  h.setFinish=(fn:()=>void)=>{finish=fn;};
  await assert.rejects(()=>h.tutor.chat('study','Spiega.',()=>{},true,'attempt'),/Tempo limite della spiegazione/);
  assert.equal(h.tutor.active.size,0);assert.equal(h.tutor.busySessions.size,0);
});


test('a direct correction can be cancelled and never saves a partial provider response as an assessment',async()=>{
  const h=harness();let listener=(event:any)=>{},finish=()=>{};
  h.tutor.create=(async()=>({subscribe(cb:any){listener=cb;return()=>{};},prompt(){return new Promise<void>(resolve=>{finish=resolve;});},async abort(){listener({type:'message_update',assistantMessageEvent:{type:'text_delta',delta:JSON.stringify({correct:true,feedback:'Partial response',rubric:'Test'})}});listener({type:'message_end',message:{role:'assistant',stopReason:'aborted'}});finish();},dispose(){}})) as any;
  const pending=h.tutor.assess('study','attempt');
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(h.tutor.busySessions.has('study'),true);assert.equal(h.tutor.active.has('study'),true);
  await h.tutor.active.get('study')!.abort();
  await assert.rejects(pending,/Correzione interrotta/);
  assert.equal(h.calls.includes('assess'),false);assert.equal(h.tutor.active.size,0);assert.equal(h.tutor.busySessions.size,0);
});

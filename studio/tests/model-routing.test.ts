import test from 'node:test';
import assert from 'node:assert/strict';
import {routingConfig,preparationRoute,expertCheckReason,sumUsage,HYBRID_ROUTING} from '../server/model-routing';
const selected={provider:'openai',id:'gpt-6.1-sol'},policy=routingConfig(HYBRID_ROUTING,selected)!;
test('bounded selection uses Luna while technical reading, authorship and every review use Sol',()=>{
  for(const kind of ['selection'])assert.equal(preparationRoute({kind,sources:[{kind:'pdf',quality:'originale'}]},policy,selected).model.id,'gpt-6-luna');
  for(const kind of ['exam_reading','evidence_reading','scope','map','map_review','chapter','repair_chapter','review_solve','review_discipline','review_didactic'])assert.equal(preparationRoute({kind},policy,selected).model.id,'gpt-6.1-sol');
  assert.equal(preparationRoute({kind:'evidence_reading',sources:[{kind:'notebook'}]},policy,selected).model.id,'gpt-6.1-sol');
  assert.equal(preparationRoute({kind:'evidence_reading',sources:[{quality:'trascrizione parziale'}]},policy,selected).model.id,'gpt-6.1-sol');
});
test('worker cannot settle exclusions; uncertainty is retained and later read by Sol',()=>{
  assert.ok(expertCheckReason('selection',{decisions:[{status:'outside'}]}));
  assert.equal(expertCheckReason('selection',{decisions:[{status:'uncertain'}]}),null);
  assert.ok(expertCheckReason('evidence_reading',{evidence:[{issues:['Formula ambiguous']}]}));
  assert.ok(expertCheckReason('evidence_reading',{evidence:[{provenance:'external'}]}));
  assert.ok(expertCheckReason('exam_reading',{questions:[{format:'open',text:'Calculate binary reduction depth',in_scope:true}]}));
  assert.ok(expertCheckReason('exam_reading',{questions:[{format:'code',text:'Implement a pipeline and discuss partitioning',in_scope:true}]}));
  assert.equal(expertCheckReason('selection',{decisions:[{status:'relevant'}]}),null);
});
test('documents consistently excluded go directly to Sol to avoid paying both models for the same full batch',()=>{
  assert.equal(preparationRoute({kind:'selection',selection_history:{reviewed:12,outside:12}},policy,selected).model.id,'gpt-6.1-sol');
  assert.equal(preparationRoute({kind:'selection',selection_history:{reviewed:12,outside:2}},policy,selected).model.id,'gpt-6-luna');
});
test('routing is opt-in and does not switch an unrelated provider',()=>{
  assert.equal(routingConfig(null,selected),null);
  assert.equal(routingConfig(HYBRID_ROUTING,{provider:'another',id:'custom'}),null);
  assert.deepEqual(preparationRoute({kind:'selection'},null,{provider:'another',id:'custom'}).model,{provider:'another',id:'custom'});
});
test('usage adds every worker and expert response without counting reasoning twice',()=>{
  const usage=sumUsage([{usage:{input:100,output:50,reasoning:20,totalTokens:150,cost:{total:.1}}},{usage:{input:200,output:100,reasoning:30,totalTokens:300,cost:{total:.2}}}]);
  assert.equal(usage.totalTokens,450);assert.equal(usage.reasoning,50);assert.equal(usage.output,150);assert.ok(Math.abs(usage.cost.total-.3)<1e-10);
});

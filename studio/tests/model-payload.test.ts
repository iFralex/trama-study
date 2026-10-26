import test from 'node:test';
import assert from 'node:assert/strict';
import {preparationModelData,deduplicateCurrentChapter,deduplicateSourceTexts} from '../server/model-payload';

import {expandSources} from './helpers/model-payload';
const text='La fonte mantiene formule, convenzioni, codice e ipotesi. '.repeat(60);
test('shared passage text expands to the identical data with context, ordering and metadata intact',()=>{
 const original={sources:[{id:'a',document:'doc',page:1,text,metadata:{fingerprint:'v1'},context:[{id:'b',page:2,text:'Adjacent '.repeat(120)}]},{id:'b',document:'doc',page:2,text:'Adjacent '.repeat(120),quality:'OCR',context:[{id:'a',page:1,text}]}],source_revisions:{doc:'fingerprint'}};
 const before=structuredClone(original),packet=deduplicateSourceTexts(original);
 assert.deepEqual(expandSources(packet),original);assert.deepEqual(original,before);
 assert.ok(JSON.stringify(packet).length<JSON.stringify(original).length);
 assert.equal(Object.keys((packet as any)._source_texts).length,2);
 assert.equal((packet.sources[0] as any).text.$ref,(packet.sources[1].context[0] as any).text.$ref);
});
test('different text for the same passage ID is never conflated and revision metadata stays distinct',()=>{
 const original={sources:[{id:'a',page:1,text,metadata:{fingerprint:'v1'}},{id:'a',page:1,text:text+'Changed formula',metadata:{fingerprint:'v2'}},{id:'a',page:1,text,metadata:{fingerprint:'v3'}}]};
 const packet=deduplicateSourceTexts(original);
 assert.equal(packet.sources[1].text,original.sources[1].text);assert.deepEqual(expandSources(packet),original);
});
test('unique sources, small text and reserved-field collisions retain the exact input format',()=>{
 for(const original of [{sources:[{id:'a',page:1,text}]},{sources:[{id:'a',page:1,text:'Short'},{id:'a',page:1,text:'Short'}]},{_source_texts:{original:'keep'},sources:[{id:'a',page:1,text},{id:'a',page:1,text}]}])assert.equal(deduplicateSourceTexts(original),original);
});

test('the complete current chapter occurs once and the plan keeps its position via a pointer',()=>{
 const chapter={id:'pram',title:'PRAM',objective:'Teach the model',sources:['a'],prerequisites:['intro']};
 const original={kind:'chapter',chapter,plan:{version:2,data:{chapters:[{id:'intro'},structuredClone(chapter),{id:'next'}],gaps:['Keep uncertainty']}}};
 const before=structuredClone(original),packet=deduplicateCurrentChapter(original) as any;
 assert.deepEqual(packet.chapter,chapter);assert.deepEqual(packet.plan.data.chapters[1],{$ref:'#/chapter'});
 const restored=structuredClone(packet);restored.plan.data.chapters[1]=structuredClone(restored.chapter);
 assert.deepEqual(restored,original);assert.deepEqual(original,before);
 assert.ok(JSON.stringify(packet).length<JSON.stringify(original).length);
});
test('chapters with the same ID but different data cannot be substituted',()=>{
 const original={chapter:{id:'pram',sources:['new']},plan:{data:{chapters:[{id:'pram',sources:['old']}]}}};
 assert.equal(deduplicateCurrentChapter(original),original);
 assert.equal(deduplicateCurrentChapter({kind:'review_solve'}).kind,'review_solve');
});

test('only local root checkpoint fields are withheld; semantic data and nested metadata stay intact',()=>{
 const task={kind:'chapter',engine:2,task_id:'immutable-id',model_key:'model',budget:32000,source_revisions:{doc:'hash'},chapter_limits:{max_blocks:48,max_characters:180000},objective:{request:'Teach PRAM',budget:'Student constraint'},sources:[{id:'a',page:1,text,metadata:{source_revisions:'source metadata'}}]};
 const original=structuredClone(task),packet=preparationModelData(task) as any;
 for(const key of ['task_id','model_key','budget','source_revisions'])assert.equal(Object.hasOwn(packet,key),false);
 const {task_id,model_key,budget,source_revisions,...semantic}=task;
 assert.deepEqual(packet,semantic);assert.deepEqual(task,original);
});
test('all three optimizations compose without changing any semantic fields or the stored task',()=>{
 const source={id:'a',document:'doc',text,page:1},chapter={id:'pram',sources:['a'],objective:'Teach PRAM'};
 const task={task_id:'immutable-id',budget:32000,source_revisions:{doc:'hash'},model_key:'model',kind:'chapter',chapter,plan:{data:{chapters:[structuredClone(chapter)],gaps:['Keep caveat']}},sources:[source,{...source,quality:'Different metadata'}]};
 const original=structuredClone(task),packet=preparationModelData(task),restored=expandSources(packet);
 restored.plan.data.chapters[0]=structuredClone(restored.chapter);
 assert.deepEqual({...restored,task_id:task.task_id,budget:task.budget,source_revisions:task.source_revisions,model_key:task.model_key},task);
 assert.deepEqual(task,original);
});

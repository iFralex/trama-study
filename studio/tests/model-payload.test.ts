import test from 'node:test';
import assert from 'node:assert/strict';
import {deduplicateCurrentChapter,deduplicateSourceTexts} from '../server/model-payload';

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

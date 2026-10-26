import test from 'node:test';
import assert from 'node:assert/strict';
import {compactChatContext,readChatContext} from '../server/chat-context';
const full={session:{mode:'learn'},activity:{prompt:'Current exercise'},attempts:[{answer:'Keep'}],interactions:[{kind:'hint'}],curriculum:{objective:{included:['PRAM'],excluded:['OpenMP']},chapter:{content:{blocks:[{text:'Keep full current chapter'}]}},diary:[{text:'Latest correction'}],preferences:[{text:'One step at a time'}],plan:{version:2,data:{chapters:[{id:'a',title:'A',sources:['source'],assessment:'Exact requirement',prerequisites:[]}],gaps:['Unresolved caveat']}},exam_profile:{questions:Array.from({length:21},(_,id)=>({id,text:'Question '+id})),formats:{open:21}},recall:null}};
test('compact context retains essential data and removed sections reconstruct exactly through tools',()=>{
 const before=structuredClone(full),packet=compactChatContext(full);
 for(const key of ['objective','chapter','diary','preferences'])assert.deepEqual((packet.curriculum as any)[key],(full.curriculum as any)[key]);
 const restored=structuredClone(packet) as any;delete restored.context_retrieval;delete restored.current_state;
 restored.curriculum.plan.data.chapters=restored.curriculum.plan.data.chapters.map((c:any)=>readChatContext(full,{section:'plan_chapter',chapter:c.id}).chapter);
 const questions:any[]=[];let offset:number|null=0;
 while(offset!==null){const page=readChatContext(full,{section:'exam_questions',offset});questions.push(...page.questions);offset=page.next_offset;}
 restored.curriculum.exam_profile.questions=questions;
 assert.deepEqual(restored,full);assert.deepEqual(full,before);
});
test('retrieval uses the current plan and fails for missing chapters or unknown sections',()=>{
 const updated=structuredClone(full);updated.curriculum.plan.version=3;updated.curriculum.plan.data.chapters[0].assessment='Corrected requirement';
 assert.equal(readChatContext(updated,{section:'plan_chapter',chapter:'a'}).chapter.assessment,'Corrected requirement');
 assert.equal(readChatContext(updated,{section:'plan_chapter',chapter:'a'}).plan_version,3);
 assert.throws(()=>readChatContext(full,{section:'plan_chapter',chapter:'other-course'}),/non disponibile/);
 assert.throws(()=>readChatContext(full,{section:'unknown'}),/non disponibile/);
});
test('exam and recall guards prevent either initial disclosure or tool retrieval',()=>{
 for(const context of [{...full,session:{mode:'exam'}},{...full,curriculum:{...full.curriculum,recall:{id:'recall'}}}]){
  assert.throws(()=>compactChatContext(context),/prova autonoma/);
  assert.throws(()=>readChatContext(context,{section:'full_context'}),/prova autonoma/);
 }
});

test('current status is explicit despite stale prose and a changed question invalidates its revision',()=>{
 const original=structuredClone(full) as any;original.curriculum.objective.confirmed=true;original.curriculum.objective.summary='Vecchia sintesi da confermare';
 const first=compactChatContext(original);
 assert.equal(first.current_state?.objective_confirmed,true);
 const changed=structuredClone(original);changed.curriculum.exam_profile.questions[0].text='New question';
 assert.notEqual(compactChatContext(changed).current_state?.exam_profile_revision,first.current_state?.exam_profile_revision);
});

test('an absent confirmation flag remains unknown instead of being treated as false',()=>{
 assert.equal(compactChatContext(full).current_state?.objective_confirmed,null);
});

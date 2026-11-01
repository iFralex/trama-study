import test from 'node:test';
import assert from 'node:assert/strict';
import {writeChapter} from '../server/preparation-chapter';
const task={kind:'chapter',task_id:'immutable',chapter:{id:'test',exam_skills:['Concept','Apply']},chapter_limits:{max_blocks:48,max_characters:180000}};
const outline=[{id:'intro',kind:'text',title:'Introduction',goal:'Explain',role:'explain',covers:[0]},{id:'worked',kind:'text',title:'Worked example',goal:'Show reasoning',role:'worked',covers:[0,1]},{id:'exercise',kind:'activity',title:'Independent',goal:'Apply',role:'independent',covers:[1]},{id:'recap',kind:'text',title:'Recap',goal:'Connect',role:'recap',covers:[0,1]}];
const blocks=outline.map(({id,kind})=>kind==='text'?{id,kind,text:'Complete content',sources:['source']}:{id,kind,spec:{kind:'open',title:'Task',prompt:'Apply',solution:'Solution',rubric:'Criteria',assumptions:'Given',origin:'generated',sources:['source']}});
const save=async(value:any)=>structuredClone(value);

test('chapter creation saves an outline and bounded batches without resending the initial task',async()=>{
 const prompts:string[]=[],saved:any[]=[];let calls=0;
 const result=await writeChapter(task,null,'Instructions',async prompt=>{prompts.push(prompt);return JSON.stringify(calls++===0?{outline}:{blocks:blocks.slice((calls-2)*2,(calls-1)*2)});},async value=>{saved.push(structuredClone(value));return save(value);},()=>false);
 assert.deepEqual(result,{blocks});assert.equal(saved.length,3);assert.equal(saved[0].blocks.length,0);assert.equal(saved[1].blocks.length,2);
 assert.match(prompts[0],/Compito \(dati\)/);assert.doesNotMatch(prompts[1],/Compito \(dati\)/);assert.doesNotMatch(prompts[2],/Compito \(dati\)/);
});
test('resuming preserves completed block bytes and requests only the missing IDs',async()=>{
 let prompt='';const recovery={version:1,outline,blocks:blocks.slice(0,2),error:''};
 const result=await writeChapter(task,recovery,'Instructions',async p=>{prompt=p;return JSON.stringify({blocks:blocks.slice(2)});},save,()=>false);
 assert.deepEqual(result,{blocks});assert.match(prompt,/Genera SOLO i blocchi richiesti/);
 assert.deepEqual(result.blocks.slice(0,2),recovery.blocks);
});
test('interruption preserves the last completed batch and a pause never commits partial content',async()=>{
 let saved:any,calls=0;
 await assert.rejects(writeChapter(task,null,'Instructions',async()=>{calls++;if(calls===3)throw Error('Tempo limite');return JSON.stringify(calls===1?{outline}:{blocks:blocks.slice(0,2)});},async value=>{saved=structuredClone(value);return save(value);},()=>false),/Tempo limite/);
 assert.equal(saved.blocks.length,2);
 let paused=false;const result=await writeChapter(task,saved,'Instructions',async()=>{paused=true;return JSON.stringify({blocks:blocks.slice(2)});},save,()=>paused);assert.equal(result,null);
});
test('outline must preserve recovery, all competencies and an independent activity',async()=>{
 let calls=0;
 await assert.rejects(writeChapter(task,{blocks:[blocks[0]],error:''},'Instructions',async()=>{calls++;return JSON.stringify({outline:outline.slice(1)});},save,()=>false),/conserva/);assert.equal(calls,2);
 await assert.rejects(writeChapter(task,null,'Instructions',async()=>JSON.stringify({outline:outline.map(r=>({...r,covers:[0]}))}),save,()=>false),/competenze/);
});
test('batch validation does not save incorrect IDs or rewrite previously completed blocks',async()=>{
 let saves=0;
 await assert.rejects(writeChapter(task,{outline,blocks:blocks.slice(0,2)},'Instructions',async()=>JSON.stringify({blocks:blocks.slice(0,2)}),async value=>{saves++;return save(value);},()=>false),/tutti e soli/);
 assert.equal(saves,1,'Only the existing valid checkpoint was saved');
});
test('complete legacy responses continue through the original final validator',async()=>{
 const result=await writeChapter(task,null,'Instructions',async()=>JSON.stringify({blocks}),async()=>{throw Error('Unexpected checkpoint');},()=>false);
 assert.deepEqual(result,{blocks});
});

const focusTask={...task,exam_policy:{version:1,questions:[{id:'q1',format:'open',text:'Describe and motivate the distinction.',label:'Exam · p. 1',sources:['exam-source']}],available_chapters:[]}};
const focus=(role:string)=>({role,exam_refs:['exam','foundation'].includes(role)?['q1']:[],reason:'Collegamento motivato alla classificazione richiesta.'});
const focusedOutline=outline.map((row,index)=>({...row,focus:focus('exam'),depends_on:index?[outline[index-1].id]:[]}));
const focusedBlocks=blocks.map(block=>block.kind==='activity'?{...block,spec:{...block.spec,origin:'adapted',exam_variant:{question:'q1',adaptation:'New scenario with the same reasoning and response structure.'}}}:block);

test('exam focus is planned once and automatically carried into every saved section',async()=>{
 let calls=0;const prompts:string[]=[];
 const result=await writeChapter(focusTask,null,'Instructions',async prompt=>{prompts.push(prompt);return JSON.stringify(calls++===0?{outline:focusedOutline}:{blocks:focusedBlocks.slice((calls-2)*2,(calls-1)*2)});},save,()=>false);
 assert.equal(result.exam_focus_version,1);
 assert.deepEqual(result.blocks[2].focus,focusedOutline[2].focus);
 assert.equal(result.blocks[2].learning_role,'independent');
 assert.deepEqual(result.blocks[2].depends_on,['worked']);
 assert.match(prompts[0],/stessa struttura/);
 assert.doesNotMatch(prompts[1],/Compito \(dati\)/);
});

test('a complementary chapter can explain its content without inventing exercises',async()=>{
 const row={...outline[0],covers:[0,1],focus:focus('support'),depends_on:[]};let calls=0;
 const result=await writeChapter(focusTask,null,'Instructions',async()=>JSON.stringify(calls++===0?{outline:[row]}:{blocks:[blocks[0]]}),save,()=>false);
 assert.equal(result.blocks.length,1);assert.equal(result.blocks[0].kind,'text');assert.equal(result.blocks[0].focus.role,'support');
});

test('exam focus rejects fabricated evidence, complementary exercises and future prerequisites',async()=>{
 for(const change of ['fake','support','future','disguised']){
  const rows=structuredClone(focusedOutline);
  if(change==='fake')rows[0].focus.exam_refs=['invented'];
  if(change==='support')rows[2].focus=focus('support');
  if(change==='future')rows[0].depends_on=['exercise'];
  if(change==='disguised')rows[2].role='explain';
  await assert.rejects(writeChapter(focusTask,null,'Instructions',async()=>JSON.stringify({outline:rows}),save,()=>false),/Indice di scrittura/);
 }
});

test('autonomous exam variants preserve the original response format',async()=>{
 const recovery={version:1,outline:focusedOutline,blocks:focusedBlocks.slice(0,2)};
 const bad={...focusedBlocks[2],spec:{...focusedBlocks[2].spec,kind:'choice'}};
 await assert.rejects(writeChapter(focusTask,recovery,'Instructions',async()=>JSON.stringify({blocks:[bad,focusedBlocks[3]]}),save,()=>false),/formato/);
});

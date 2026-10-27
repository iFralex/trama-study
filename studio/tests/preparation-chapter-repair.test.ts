import test from 'node:test';
import assert from 'node:assert/strict';
import {chapterRepairTargets,chapterRepairPrompt,repairChapterBlocks} from '../server/preparation-chapter-repair';
import {runPreparation} from '../server/preparation-engine';
const task={task_id:'immutable',kind:'repair_chapter',chapter:{id:'chapter',title:'Chapter'},draft_revision:2,objective:{included:['PRAM']},originals:[{id:'a',text:'Source A'},{id:'b',text:'Source B'}],reviews:{discipline:{issues:[{block:'second',severity:'blocking',message:'Fix formula',sources:['b']}]},didactic:{issues:[{block:'third',severity:'warning',message:'Explain notation',sources:['a']}]}},draft:{blocks:[{id:'first',kind:'text',text:'Keep this unchanged',sources:['a']},{id:'second',kind:'text',text:'Formula',sources:['b']},{id:'third',kind:'text',text:'Notation',sources:['a']},{id:'last',kind:'text',text:'Keep the ending',sources:['a']}]}};
function answer(prompt:string){const data=JSON.parse(prompt.split('Dati della correzione:\n')[1]);return {blocks:[{...data.block,text:data.block.text+' corrected'}]};}
test('repair targets both reviews and requests one block without copying the chapter',()=>{
 assert.deepEqual(chapterRepairTargets(task),['second','third']);
 const prompt=chapterRepairPrompt(task,'second'),data=JSON.parse(prompt.split('Dati della correzione:\n')[1]);
 assert.equal(data.block.id,'second');assert.deepEqual(data.originals,[task.originals[1]]);
 assert.deepEqual(data.reviews.discipline.issues,task.reviews.discipline.issues);
 assert.equal(data.draft,undefined);assert.equal(data.profile,undefined);assert.match(prompt,/un unico blocco/);
});
test('completed replacements survive interruption and untouched blocks stay identical',async()=>{
 let checkpoint:any,calls=0;
 await assert.rejects(repairChapterBlocks(task,undefined,async prompt=>{if(++calls===2)throw Error('Provider timeout');return answer(prompt);},async value=>{checkpoint=structuredClone(value);},()=>false),/Provider timeout/);
 assert.equal(checkpoint.blocks.length,1);
 const prompts:string[]=[];const result=await repairChapterBlocks(task,checkpoint,async prompt=>{prompts.push(prompt);return answer(prompt);},async()=>{},()=>false);
 assert.equal(prompts.length,1);assert.equal(answer(prompts[0]).blocks[0].id,'third');
 assert.deepEqual(result.blocks[0],task.draft.blocks[0]);assert.deepEqual(result.blocks[3],task.draft.blocks[3]);assert.equal(result.blocks[1].text,'Formula corrected');
});
test('resumed repair supplies complete source texts and retries only pending replacements',async()=>{
 const saved={version:1,targets:['second','third'],blocks:[{...task.draft.blocks[1],text:'Validated correction'}],pending_blocks:[{...task.draft.blocks[2],text:'Correction awaiting source verification'}]};
 const prompts:string[]=[],loaded:string[][]=[];
 const result=await repairChapterBlocks(task,saved,async prompt=>{prompts.push(prompt);return answer(prompt);},async()=>{},()=>false,async refs=>{loaded.push(refs);return refs.map(id=>({id,text:'Full source '+id}));});
 assert.deepEqual(loaded,[['a']]);assert.equal(prompts.length,1);
 const data=JSON.parse(prompts[0].split('Dati della correzione:\n')[1]);
 assert.equal(data.block.text,saved.pending_blocks[0].text);assert.deepEqual(data.originals,[{id:'a',text:'Full source a'}]);
 assert.deepEqual(result.blocks[1],saved.blocks[0]);assert.equal(result.blocks[2].text,'Correction awaiting source verification corrected');
 assert.equal(data.context_blocks.find((b:any)=>b.id==='second').text,'Validated correction');
});
test('repair rejects changed IDs and incomplete activities with one bounded retry',async()=>{
 let calls=0,saves=0;
 await assert.rejects(repairChapterBlocks(task,null,async()=>{calls++;return {blocks:[task.draft.blocks[0]]};},async()=>{saves++;},()=>false),/stesso id/);
 assert.equal(calls,2);assert.equal(saves,0);
 const activity=structuredClone(task) as any;activity.draft.blocks[1]={id:'second',kind:'activity',spec:{prompt:'P',solution:'S',rubric:'R',sources:['b']}};
 await assert.rejects(repairChapterBlocks(activity,null,async()=>({blocks:[{id:'second',kind:'activity',spec:{prompt:'P'}}]}),async()=>{},()=>false),/incompleta/);
});
test('pause preserves checkpoints and never returns a partial chapter to commit',async()=>{
 let paused=false,saved:any;
 const result=await repairChapterBlocks(task,null,async p=>answer(p),async checkpoint=>{saved=checkpoint;paused=true;},()=>paused);
 assert.equal(result,null);assert.equal(saved.blocks.length,1);
});
test('engine saves block checkpoints and submits the complete chapter to normal validation',async()=>{
 let complete=false,committed:any;const saved:any[]=[],sessions:any[]=[];
 const bridge={async call(method:string,args:any={}){
  if(method==='course_path_view')return {sid:'session',status:'error'};
  if(method==='course_status')return {};
  if(method==='course_peek_task')return complete?{kind:'done'}:task;
  if(method==='course_task')return task;
  if(method==='preparation_begin')return {metrics:{}};
  if(method==='source')return {id:args.source_id,text:'Original '+args.source_id};
  if(method==='preparation_read')return {};
  if(method==='preparation_usage'){if(args.metrics.repair_checkpoint)saved.push(args.metrics.repair_checkpoint);return {};}
  if(method==='preparation_commit'){committed=args.result;complete=true;return {};}
  if(['preparation_metric','preparation_model_call'].includes(method))return {};
  throw Error(method);
 }};
 const tutor={busySessions:new Set(),preparationOwner:undefined,async preparationRouting(){return null;},async preparationBudget(){return {input:32000,context:64000,output:8192,key:'test',model:{provider:'test',id:'test'}};},async create(){let emit=(event:any)=>{};const session={disposed:false,subscribe(cb:any){emit=cb;return()=>{};},async prompt(text:string){emit({type:'message_update',assistantMessageEvent:{type:'text_delta',delta:JSON.stringify(answer(text))}});},dispose(){this.disposed=true;}};sessions.push(session);return session;}};
 await runPreparation(bridge as any,tutor as any,'path',{paused:false});
 assert.equal(saved.length,2);assert.equal(saved[0].blocks.length,1);assert.equal(saved[1].blocks.length,2);
 assert.equal(committed.blocks.length,task.draft.blocks.length);assert.deepEqual(committed.blocks[0],task.draft.blocks[0]);
 assert.equal(sessions.length,2);assert.ok(sessions.every(s=>s.disposed));
});

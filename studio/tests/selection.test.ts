import test from 'node:test';
import assert from 'node:assert/strict';
import {selectionPacket,validateDecisions,exclusionReview,mergeExclusions} from '../server/selection';
const task={kind:'selection',objective:{request:'Primo parziale',summary:'Il confine effettivo prevale sul calendario.',included:['PRAM'],excluded:['HLS'],reserved:['PRIVATE_DOC']},previews:[{id:'a',preview:'PRAM'},{id:'b',preview:'HLS'},{id:'c',preview:'testo misto'}],exam_profile:{total:12,formats:{open:12},skills:{PRAM:12},questions:[{text:'LONG_EXAM_TEXT'}]}};
const decision=(source:string,status='relevant')=>({source,status,reason:'Contenuto confrontato con il perimetro.',skills:['PRAM']});
const worker={decisions:[decision('a'),decision('b','outside'),decision('c','uncertain')]};
test('selection keeps scope rationale and sources but omits exam text and reservation metadata',()=>{
 const packet=selectionPacket(task);assert.equal(packet.objective.summary,task.objective.summary);assert.deepEqual(packet.previews,task.previews);assert.doesNotMatch(JSON.stringify(packet),/LONG_EXAM_TEXT|PRIVATE_DOC/);
});
test('expert sees only proposed exclusions; merging preserves the exact other decisions',()=>{
 const review=exclusionReview(task,worker)!;assert.deepEqual(review.previews.map((s:any)=>s.id),['b']);
 assert.equal((review as any).decisions,undefined);const merged=mergeExclusions(task,worker,{decisions:[decision('b','prerequisite')]});
 assert.strictEqual(merged.decisions[0],worker.decisions[0]);assert.strictEqual(merged.decisions[2],worker.decisions[2]);assert.equal(merged.decisions[1].status,'prerequisite');assert.equal(worker.decisions[1].status,'outside');
});
test('uncertainty retains a source without an immediate duplicate expert pass',()=>{
 assert.equal(exclusionReview(task,{decisions:task.previews.map(s=>decision(s.id,'uncertain'))}),null);
});
test('partial, duplicate, alien or malformed decisions cannot commit or overwrite unreviewed decisions',()=>{
 for(const result of [{},{decisions:[decision('a')]},{decisions:[decision('a'),decision('a'),decision('c')]},{decisions:[decision('a'),decision('alien'),decision('c')]},{decisions:[decision('a','mastered'),decision('b'),decision('c')]}])assert.throws(()=>validateDecisions(task,result));
 assert.throws(()=>mergeExclusions(task,worker,{decisions:[decision('a')]}));
 assert.throws(()=>mergeExclusions(task,worker,{decisions:[decision('b'),decision('c')]}));
});

test('truncated previews cannot discard the unobserved part of a source',()=>{
 const truncated={previews:[{id:'long',preview:'Administrative opening only',truncated:true}]};
 assert.throws(()=>validateDecisions(truncated,{decisions:[decision('long','outside')]}),/troncato/);
 assert.doesNotThrow(()=>validateDecisions(truncated,{decisions:[decision('long','uncertain')]}));
});

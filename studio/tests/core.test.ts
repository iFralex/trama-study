import {test} from 'node:test';
import assert from 'node:assert/strict';
import {simulate} from '../src/simulator';
import {artifactDocument,validArtifactEvent} from '../src/artifact';
import {fsrs,createEmptyCard,Rating} from 'ts-fsrs';

test('reduction result, work, depth and finite processors',()=>{
  const result=simulate([1,2,3,4,5,6,7,8],4,'reduction','EREW');
  assert.deepEqual(result.result,[36]);assert.equal(result.work,7);assert.equal(result.depth,3);assert.equal(result.time,3);
  assert.equal(simulate(Array.from({length:16},(_,i)=>i),2,'reduction','CREW').time,8);
  assert.deepEqual(simulate([1,2,3],2,'reduction','CREW').result,[6]);
});
test('scan uses immutable previous levels and respects the stated model',()=>{
  const result=simulate([1,2,3,4,5,6,7,8],4,'scan','CREW');
  assert.deepEqual(result.result,[1,3,6,10,15,21,28,36]);assert.equal(result.work,17);assert.equal(result.time,5);
  assert.equal(simulate([1,2,3,4],2,'scan','EREW').supported,false);
  assert.equal(simulate([1,2,3,4],1,'scan','EREW').supported,true);
});
test('artifact document isolates code and installs an observable bridge',()=>{
  const html=artifactDocument('<html><head></head><body><script>window.a=1</script></body></html>','token-123');
  assert.match(html,/connect-src 'none'/);assert.match(html,/window.study=/);assert.match(html,/data-key/);assert.match(html,/nonce="token123"/);
});
test('events require the actual iframe, nonce, allowed action and object payload',()=>{
  const frame={} as Window;const data={channel:'polimi-study',token:'abc',kind:'change',payload:{processors:4}};
  assert.equal(validArtifactEvent({source:frame,data} as MessageEvent,frame,'abc'),true);
  assert.equal(validArtifactEvent({source:{},data} as MessageEvent,frame,'abc'),false);
  assert.equal(validArtifactEvent({source:frame,data:{...data,kind:'award_mastery'}} as MessageEvent,frame,'abc'),false);
});
test('FSRS schedules a verified recall and restores JSON dates',()=>{
  const date=new Date('2026-10-16T12:00:00Z');const first=fsrs().next(createEmptyCard(date),date,Rating.Good);
  const card=JSON.parse(JSON.stringify(first.card));card.due=new Date(card.due);if(card.last_review)card.last_review=new Date(card.last_review);
  const next=fsrs().next(card,card.due,Rating.Good);assert.ok(next.card.due>card.due);
});

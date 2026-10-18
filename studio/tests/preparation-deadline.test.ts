import test from 'node:test';
import assert from 'node:assert/strict';
import {promptWithDeadline,PreparationTimeout} from '../server/preparation-deadline';
test('each repair has a fresh deadline and completed calls leave no abort timer',async()=>{
 let aborted=0,calls=0;const began=Date.now();
 const session={async prompt(){calls++;await new Promise(r=>setTimeout(r,35));},async abort(){aborted++;}};
 await promptWithDeadline(session,'initial',50);await promptWithDeadline(session,'repair',50);
 await new Promise(r=>setTimeout(r,60));assert.equal(calls,2);assert.equal(aborted,0);assert.ok(Date.now()-began>50,'Combined calls exceed one request deadline');
});
test('deadline cancels and reports a useful error even if the provider never closes its stream',async()=>{
 let aborted=0;
 const session={prompt:()=>new Promise(()=>{}),async abort(){aborted++;}};
 await assert.rejects(promptWithDeadline(session,'request',10),error=>error instanceof PreparationTimeout&&/checkpoint/.test(error.message));
 assert.equal(aborted,1);
 await assert.rejects(promptWithDeadline(session,'expired task',0),PreparationTimeout);assert.equal(aborted,1);
});
test('provider failures retain their cause instead of becoming timeouts',async()=>{
 const cause=Error('Subscription Sharing usage limit');let aborted=0;
 await assert.rejects(promptWithDeadline({async prompt(){throw cause;},async abort(){aborted++;}},'request',100),error=>error===cause);
 assert.equal(aborted,0);
});

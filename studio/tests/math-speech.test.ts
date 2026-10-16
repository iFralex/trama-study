import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mathSpeech} from '../server/math-speech';

test('whole formulas receive local Italian speech without a duplicate TeX annotation',async()=>{
 const linear=await mathSpeech('T(n)=an+b');assert.equal(linear.locale,'it');assert.equal(linear.speech,'T di n uguale a a per n più b');assert.equal(linear.speech.split('uguale').length,2);
 const fraction=await mathSpeech(String.raw`\frac{a+b}{c}`);assert.match(fraction.speech,/frazione/);assert.match(fraction.speech,/numeratore a più b e denominatore c/);assert.doesNotMatch(fraction.speech,/back slash|frac parentesi/);
 assert.match((await mathSpeech('x^2')).speech,/quadrato/);
 assert.match((await mathSpeech('x_i')).speech,/pedice i/);
 assert.deepEqual(await mathSpeech('T(n)=an+b'),linear);
 await assert.rejects(()=>mathSpeech('x'.repeat(4001)),/troppo lunga/);
});

// Distinguish function arguments from multiplication without removing grouping.
test('natural speech distinguishes the cost function and implicit products',async()=>{
 assert.equal((await mathSpeech('f(x)=2x')).speech,'f di x uguale a 2 per x');
 assert.equal((await mathSpeech('a(n+b)')).speech,'a per parentesi tonda aperta n più b parentesi tonda chiusa');
 assert.equal((await mathSpeech('T(n/2)+n')).speech,'T di parentesi tonda aperta n diviso per 2 parentesi tonda chiusa più n');
 assert.equal((await mathSpeech('T+an')).speech,'T più a per n');
 assert.equal((await mathSpeech(String.raw`a\times n`)).speech,'a per n');
});

test('inequality operators are spoken rather than skipped',async()=>{
 assert.equal((await mathSpeech('i ≤ n')).speech,'i minore o uguale a n');
 assert.equal((await mathSpeech(String.raw`i\le n`)).speech,'i minore o uguale a n');
 assert.equal((await mathSpeech('i ≥ n')).speech,'i maggiore o uguale a n');
 assert.equal((await mathSpeech('i ≠ n')).speech,'i diverso da n');
});

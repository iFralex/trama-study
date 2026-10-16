import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mathSpeech} from '../server/math-speech';

test('whole formulas receive local Italian speech without a duplicate TeX annotation',async()=>{
 const linear=await mathSpeech('T(n)=an+b');assert.equal(linear.locale,'it');assert.match(linear.speech,/T maiuscola/);assert.match(linear.speech,/uguale a a n più b/);assert.equal(linear.speech.split('uguale').length,2);
 const fraction=await mathSpeech(String.raw`\frac{a+b}{c}`);assert.match(fraction.speech,/frazione/);assert.match(fraction.speech,/fratto c/);assert.doesNotMatch(fraction.speech,/back slash|frac parentesi/);
 assert.match((await mathSpeech('x^2')).speech,/quadrato/);
 assert.match((await mathSpeech('x_i')).speech,/pedice i/);
 assert.deepEqual(await mathSpeech('T(n)=an+b'),linear);
 await assert.rejects(()=>mathSpeech('x'.repeat(4001)),/troppo lunga/);
});

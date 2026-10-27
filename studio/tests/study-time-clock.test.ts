import test from 'node:test';
import assert from 'node:assert/strict';
import {StudyClock} from '../src/study-time-clock';

test('foreground time is counted while background and idle gaps remain excluded',()=>{
 const clock=new StudyClock(0,100000);clock.advance(0,100000,true);clock.advance(5000,105000,true);clock.advance(10000,110000,false);
 assert.deepEqual(clock.take(),{started:100000,ended:110000,seconds:10});
 clock.advance(20000,120000,false);assert.equal(clock.take(),null);
 clock.advance(25000,125000,true);clock.advance(30000,130000,true);assert.deepEqual(clock.take(),{started:125000,ended:130000,seconds:5});
});
test('sleep and wall-clock jumps split windows rather than charging the gap',()=>{
 const clock=new StudyClock(0,100000);clock.advance(0,100000,true);clock.advance(5000,105000,true);clock.advance(600000,700000,true);clock.advance(605000,705000,true);
 assert.deepEqual(clock.take(),{started:100000,ended:105000,seconds:5});assert.deepEqual(clock.take(),{started:700000,ended:705000,seconds:5});
 clock.advance(610000,50000,true);clock.advance(615000,55000,true);assert.deepEqual(clock.take(),{started:50000,ended:55000,seconds:5});
});
test('flushing twice is idempotent and subsecond transitions cannot leave a stale window',()=>{
 const clock=new StudyClock(0,100000);clock.advance(0,100000,true);clock.advance(250,100250,false);
 assert.deepEqual(clock.take(),{started:100000,ended:100250,seconds:.25});assert.equal(clock.take(),null);
 clock.advance(10000,110000,true);clock.advance(15000,115000,true);assert.equal(clock.take()?.seconds,5);
});

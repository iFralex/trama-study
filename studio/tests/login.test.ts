import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {ModelRuntime} from '@earendil-works/pi-coding-agent';
import {installationLoginOptions} from '../server/login';
import type {Bridge} from '../server/bridge';

test('actual ChatGPT OAuth receives a stable installation UUID and reaches authorization',async()=>{
  const root=await mkdtemp(path.join(os.tmpdir(),'studio-login-'));
  const identity='ebfa5e8b-7cf6-4fb3-b75e-7c2577810b25';
  const bridge={async call(method:string){assert.equal(method,'installation_id');return identity;}} as unknown as Bridge;
  try{
    const runtime=await ModelRuntime.create({authPath:path.join(root,'auth.json'),modelsPath:null,refreshOnCreate:false});
    const options=await installationLoginOptions(bridge);
    assert.equal(options.getDeviceId(),(await installationLoginOptions(bridge)).getDeviceId());
    const abort=new AbortController();let reached=false;
    await assert.rejects(()=>runtime.login('openai','oauth',{
      signal:abort.signal,
      notify(event){if(event.type==='auth_url'){
        const url=new URL(event.url);assert.equal(url.searchParams.get('ext_agent_host_id'),'urn:uuid:'+identity);
        assert.equal(url.searchParams.get('agent_name_hint'),'Polimi Studio');reached=true;abort.abort();
      }},
      async prompt(){throw Error('Test cancelled before account authorization');},
    },options),/cancelled|aborted/i);
    assert.equal(reached,true);
  }finally{await rm(root,{recursive:true,force:true});}
});

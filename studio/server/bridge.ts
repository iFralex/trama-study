import {spawn,ChildProcessWithoutNullStreams} from 'node:child_process';
import {createInterface} from 'node:readline';
import {randomUUID} from 'node:crypto';
export class Bridge {
  child:ChildProcessWithoutNullStreams;
  pending=new Map<string,{resolve:(v:any)=>void,reject:(e:Error)=>void}>();
  constructor(python:string,project:string,root?:string){
    this.child=spawn(python,['-m','polimi_lectures.study',...(root?['--root',root]:[])],{cwd:project,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
    createInterface({input:this.child.stdout}).on('line',line=>{try{const msg=JSON.parse(line),p=this.pending.get(msg.id);if(p){this.pending.delete(msg.id);msg.error?p.reject(Error(msg.error)):p.resolve(msg.result);}}catch{process.stderr.write('Risposta bridge non valida.\n');}});
    this.child.stderr.on('data',chunk=>process.stderr.write(chunk));
    const stop=(error:Error)=>{for(const p of this.pending.values())p.reject(error);this.pending.clear();};
    this.child.on('error',stop);this.child.on('exit',()=>stop(Error('Servizio dati interrotto. Riavvia Studio.')));
  }
  call(method:string,args:Record<string,unknown>={}):Promise<any>{
    return new Promise((resolve,reject)=>{const id=randomUUID();this.pending.set(id,{resolve,reject});this.child.stdin.write(JSON.stringify({id,method,args})+'\n',error=>{if(error){this.pending.delete(id);reject(error);}});});
  }
  close(){this.child.kill();}
}

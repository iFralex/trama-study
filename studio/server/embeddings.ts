import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {existsSync} from 'node:fs';
import path from 'node:path';
import {Bridge} from './bridge';

export class Embeddings {
  child?:ReturnType<typeof spawn>;pending=new Map<number,{resolve:(v:any)=>void,reject:(e:Error)=>void}>();sequence=0;
  ready?:Promise<string>;model='';jobs=new Map<string,{running:boolean,pending:number,total:number,error?:string}>();
  constructor(public bridge:Bridge,public root:string,public project:string){}
  call(method:string,args:any={}):Promise<any>{return new Promise((resolve,reject)=>{const id=++this.sequence;this.pending.set(id,{resolve,reject});this.child!.stdin!.write(JSON.stringify({id,method,args})+'\n');});}
  init(){return this.ready??=this.start().catch(error=>{this.ready=undefined;throw error;});}
  async start(){
    const python=path.join(this.root,'.state/embeddings-runtime/bin/python');
    if(!existsSync(python))throw Error('Ambiente embeddings assente. Avvia Studio.command per prepararlo.');
    this.child=spawn(python,['-m','polimi_lectures.embedding_worker','--cache',path.join(this.root,'.state/embedding-models')],{cwd:this.project,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
    createInterface({input:this.child.stdout!}).on('line',line=>{try{const msg=JSON.parse(line),p=this.pending.get(msg.id);if(p){this.pending.delete(msg.id);msg.error?p.reject(Error(msg.error)):p.resolve(msg.result);}}catch{}});
    this.child.stderr!.on('data',()=>{}); // Model download messages must not leak into JSON RPC.
    const stop=(error:Error)=>{for(const p of this.pending.values())p.reject(error);this.pending.clear();this.ready=undefined;this.model='';};
    this.child.on('error',stop);this.child.on('exit',()=>stop(Error('Servizio embeddings interrotto. La ricerca testuale rimane disponibile.')));
    this.model=(await this.call('info')).model;return this.model;
  }
  index(course:string){
    if(this.jobs.get(course)?.running)return;
    const job={running:true,pending:0,total:0,error:undefined as string|undefined};this.jobs.set(course,job);
    void (async()=>{try{await this.init();while(true){const batch=await this.bridge.call('embedding_batch',{course,model:this.model});job.pending=batch.pending;job.total=batch.total;if(!batch.items.length)break;const items=await this.call('documents',{items:batch.items});await this.bridge.call('save_embeddings',{model:this.model,items});await new Promise(resolve=>setTimeout(resolve,10));}}catch(error:any){job.error=error.message;}finally{job.running=false;}})();
  }
  async search(course:string,query:string,limit=8,mode='learn'){
    if(mode==='exam')throw Error('Ricerca sospesa durante la simulazione.');
    const lexical=await this.bridge.call('search',{course,query,limit:20,mode});
    if(!this.model){void this.init().catch(()=>{});return lexical.slice(0,limit).map((s:any)=>({...s,retrieval:'text-only'}));}
    try{
      const query_vector=await this.call('query',{query});
      const semantic=await this.bridge.call('semantic_search',{course,query_vector,model:this.model,limit:30,mode});
      const scores=new Map<string,{source:any,score:number}>();
      // Reciprocal rank fusion; exact lexical results have a modest preference.
      for(const [list,weight] of [[lexical,1.2],[semantic,1]] as [any[],number][]){list.forEach((source,index)=>{const old=scores.get(source.id);scores.set(source.id,{source:{...old?.source,...source},score:(old?.score??0)+weight/(30+index+1)});});}
      const counts=new Map<string,number>();return [...scores.values()].sort((a,b)=>b.score-a.score).filter(({source})=>{const n=counts.get(source.document)??0;counts.set(source.document,n+1);return n<3;}).slice(0,Math.max(1,Math.min(limit,20))).map(({source,score})=>({...source,retrieval:'hybrid',retrieval_score:score}));
    }catch{return lexical.slice(0,limit).map((s:any)=>({...s,retrieval:'text-only'}));}
  }
  close(){this.child?.kill();}
}

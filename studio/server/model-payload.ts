import {isDeepStrictEqual} from 'node:util';

/** Local checkpoint identity and integrity stay on the original task, never in model context. */
export function preparationModelData<T>(task:T):T{
  const {task_id,model_key,budget,source_revisions,...content}=task as any;
  return deduplicateSourceTexts(deduplicateCurrentChapter(content)) as T;
}

/** The canonical chapter stays at /chapter; its exact copy in the plan becomes a pointer. */
export function deduplicateCurrentChapter<T>(data:T):T{
  const task=data as any,chapters=task?.plan?.data?.chapters;
  if(!task?.chapter||!Array.isArray(chapters))return data;
  const matches=chapters.map((chapter:any)=>isDeepStrictEqual(chapter,task.chapter));
  if(!matches.some(Boolean))return data;
  return {...task,plan:{...task.plan,data:{...task.plan.data,chapters:chapters.map((chapter:any,index:number)=>matches[index]?{$ref:'#/chapter'}:chapter)}}};
}

/** Share only identical passage text. Every occurrence keeps its own metadata and position. */
export function deduplicateSourceTexts<T>(data:T):T{
  if(!data||typeof data!=='object'||Array.isArray(data)||Object.hasOwn(data,'_source_texts'))return data;
  const passage=(value:any)=>value&&typeof value==='object'&&!Array.isArray(value)&&typeof value.id==='string'&&typeof value.text==='string'&&value.text.length>=200&&['document','page','start','end'].some(key=>Object.hasOwn(value,key));
  const counts=new Map<string,number>();
  const key=(value:any)=>JSON.stringify([value.id,value.text]);
  const count=(value:any)=>{
    if(!value||typeof value!=='object')return;
    if(passage(value))counts.set(key(value),(counts.get(key(value))??0)+1);
    Object.values(value).forEach(count);
  };
  count(data);
  const texts:Record<string,string>={},references=new Map<string,string>();
  const replace=(value:any):any=>{
    if(!value||typeof value!=='object')return value;
    if(Array.isArray(value))return value.map(replace);
    const duplicate=passage(value)&&(counts.get(key(value))??0)>1;
    let ref:string|undefined;
    if(duplicate){
      ref=references.get(key(value));
      if(!ref){ref='s'+(references.size+1);references.set(key(value),ref);texts[ref]=value.text;}
    }
    return Object.fromEntries(Object.entries(value).map(([name,item])=>[name,name==='text'&&ref?{$ref:'#/_source_texts/'+ref}:replace(item)]));
  };
  const transformed=replace(data);
  if(!references.size)return data;
  const packet={...transformed,_source_texts:texts};
  // Tiny repetitions need not pay for a dictionary. Never alter stored task objects.
  return JSON.stringify(packet).length<JSON.stringify(data).length?packet as T:data;
}

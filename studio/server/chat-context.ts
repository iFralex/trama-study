import {createHash} from 'node:crypto';

/** Current learning data stays complete; other plan entries and exam questions remain retrievable. */
function allowed(context:any){
  if(context.session?.mode==='exam'||context.curriculum?.recall)throw Error('Recupero del contesto sospeso durante una prova autonoma.');
}
export function compactChatContext(context:any){
  allowed(context);
  const curriculum=context.curriculum;
  if(!curriculum)return context;
  const plan=curriculum.plan,profile=curriculum.exam_profile;
  return {...context,curriculum:{...curriculum,
    plan:plan?{...plan,data:{...plan.data,chapters:plan.data.chapters.map((c:any)=>({id:c.id,title:c.title,prerequisites:c.prerequisites,details:{tool:'read_context',section:'plan_chapter',chapter:c.id}}))}}:plan,
    exam_profile:profile?{...profile,questions:{count:profile.questions.length,details:{tool:'read_context',section:'exam_questions',offset:0}}}:profile,
  },current_state:{objective_confirmed:typeof curriculum.objective?.confirmed==='boolean'?curriculum.objective.confirmed:null,plan_version:plan?.version,exam_profile_revision:createHash('sha256').update(JSON.stringify(profile??null)).digest('hex').slice(0,16)},context_retrieval:{instruction:'I dettagli dei capitoli del piano e i quesiti del profilo sono disponibili integralmente con read_context. Recuperali prima di rispondere quando servono. Il capitolo corrente, obiettivo, diario, preferenze, tentativi ed eventi sono già integrali. Le risposte dello strumento usano lo stato corrente, che prevale sullo storico. current_state contiene lo stato attuale: objective_confirmed prevale su frasi storiche di summary o diario che chiedono ancora conferma. Se exam_profile_revision cambia, recupera nuovamente i quesiti necessari prima di citarli.',fallback:{tool:'read_context',section:'full_context'}}};
}
export function readChatContext(context:any,request:{section:string,chapter?:string,offset?:number}){
  allowed(context);
  if(request.section==='full_context')return context;
  if(request.section==='plan_chapter'){
    const chapter=context.curriculum?.plan?.data?.chapters.find((c:any)=>c.id===request.chapter);
    if(!chapter)throw Error('Capitolo non disponibile nel percorso corrente.');
    return {chapter,plan_version:context.curriculum.plan.version};
  }
  if(request.section==='exam_questions'){
    const questions=context.curriculum?.exam_profile?.questions??[],offset=Math.max(0,Math.floor(request.offset??0));
    return {questions:questions.slice(offset,offset+10),total:questions.length,next_offset:offset+10<questions.length?offset+10:null};
  }
  throw Error('Sezione di contesto non disponibile.');
}

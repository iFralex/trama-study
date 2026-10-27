import React,{useCallback,useEffect,useRef,useState} from 'react';
import {StudyClock} from './study-time-clock';

async function request(url:string,body?:any){
 const response=await fetch('/api'+url,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),keepalive:body!==undefined});
 const data=await response.json();if(!response.ok)throw Error(data.error??'Salvataggio del tempo da riprovare.');return data;
}
export function timeRange(value:any){
 if(!value)return 'Stima in preparazione';
 const amount=(n:number,up:boolean)=>{const rounded=n<10?Math.round(n):(up?Math.ceil(n/5):Math.floor(n/5))*5;if(rounded<60)return rounded+' min';const h=Math.floor(rounded/60),m=rounded%60;return h+' h'+(m?' '+m+' min':'');};
 if(value.high===0)return '0 min';
 return value.low===value.high?amount(value.high,true):amount(value.low,false)+' – '+amount(value.high,true);
}
export function useStudyTime(path:any,view:any){
 const [estimate,setEstimate]=useState<any>(null),[error,setError]=useState(''),[working,setWorking]=useState(false);
 const latest=useRef(path);latest.current=path;const generation=useRef(0),lastTarget=useRef('');
 const refresh=useCallback(async()=>{
  const p=latest.current;if(!p)return;const token=++generation.current;
  try{const data=await request('/paths/'+p.id+'/study-time'+(p.sid?'?sid='+encodeURIComponent(p.sid)+(p.current?'&chapter='+encodeURIComponent(p.current.chapter)+'&version='+p.current.version:''):''));if(token===generation.current){setEstimate(data.version?data:null);setError('');}}catch(e:any){if(token===generation.current)setError(e.message);}
 },[]);
 const key=JSON.stringify([path?.id,path?.sid,path?.plan?.version,path?.current?.chapter,path?.current?.version,path?.chapters?.map((c:any)=>[c.id,c.version]),view?.session?.id===path?.sid?view?.attempts?.map((a:any)=>[a.id,a.grade?.correct,a.grade?.status]):null]);
 useEffect(()=>{const target=JSON.stringify([path?.id,path?.sid,path?.current?.chapter,path?.current?.version]);if(lastTarget.current!==target){setEstimate(null);setError('');lastTarget.current=target;}if(path?.plan)void refresh();return()=>{generation.current++;};},[key,refresh]);
 const mark=async(block:string,status:string,visible?:{path:string,sid:string,chapter:string,version:number})=>{
  const p=latest.current;if(!visible&&!p?.current)return;const target=visible??{path:p.id,sid:p.sid,chapter:p.current.chapter,version:p.current.version};const same=p?.id===target.path&&p?.sid===target.sid&&p?.current?.chapter===target.chapter&&p?.current?.version===target.version;setWorking(true);const token=same?++generation.current:-1;
  try{const data=await request('/sessions/'+target.sid+'/study-time/mark',{chapter:target.chapter,version:target.version,block,status});if(token===generation.current){setEstimate(data);setError('');}}catch(e:any){if(token===generation.current)setError(e.message);}finally{setWorking(false);}
 };
 const settings=async(daily_minutes:number,tracking:boolean)=>{
  const p=latest.current;if(!p)return;setWorking(true);const token=++generation.current;
  try{const data=await request('/paths/'+p.id+'/study-time',{daily_minutes,tracking,sid:p.sid,...(p.current?{chapter:p.current.chapter,version:p.current.version}:{})});if(token===generation.current){setEstimate(data);setError('');}}catch(e:any){if(token===generation.current)setError(e.message);}finally{setWorking(false);}
 };
 return {estimate,error,working,refresh,mark,settings};
}

export function StudyTimeOverview({data,onSettings,working}:{data:any,onSettings:(minutes:number,tracking:boolean)=>Promise<void>,working:boolean}){
 const [minutes,setMinutes]=useState(30),[tracking,setTracking]=useState(true);
 useEffect(()=>{if(data){setMinutes(data.daily_minutes);setTracking(data.tracking);}},[data?.daily_minutes,data?.tracking]);
 if(!data?.available)return <p className="quiet">La stima di studio sarà disponibile quando il percorso avrà un indice dei capitoli.</p>;
 return <section className="study-time-overview" aria-label="Tempo di studio del percorso">
  <div className="study-time-totals"><div><span className="eyebrow">PRIMO STUDIO · INTERO PERCORSO</span><strong>{timeRange(data.total)}</strong></div><div><span className="eyebrow">LAVORO RIMANENTE</span><strong>{timeRange(data.remaining)}</strong></div></div>
  <p>{data.study_days.low===data.study_days.high?data.study_days.low:data.study_days.low+'–'+data.study_days.high} giorni di studio a {data.daily_minutes} min/giorno{data.default_daily_minutes?' (ritmo iniziale modificabile)':''}.</p>
  <p className="quiet">{data.forecast_chapters?data.forecast_chapters+(data.forecast_chapters===1?' capitolo ancora da creare':' capitoli ancora da creare')+': previsione dal programma, con intervallo più ampio.':'Stima sui contenuti disponibili.'} {data.calibrated_samples>=3?'Taratura locale sui blocchi studiati.':'Taratura iniziale; si affina con lo studio.'}</p>
  <details><summary>Dettagli e ritmo di studio</summary><p>{data.scope}</p><p>Ripassi già programmati: {data.scheduled_recalls.count} · {timeRange(data.scheduled_recalls.time)} aggiuntivi. I richiami futuri dipenderanno dalle risposte.</p><p>Tempo rilevato in primo piano: {Math.round(data.recorded_minutes)} min. È un dato approssimativo per tarare le stime, non una misura della comprensione.</p>
   <form onSubmit={e=>{e.preventDefault();void onSettings(minutes,tracking);}}><label>Minuti di studio al giorno<input type="number" min="5" max="600" value={minutes} required onChange={e=>setMinutes(Number(e.target.value))}/></label><label className="course-check"><input type="checkbox" checked={tracking} onChange={e=>setTracking(e.target.checked)}/>Rileva localmente il tempo in primo piano</label><button disabled={working}>Salva ritmo e rilevazione</button></form>
   <p className="quiet">Calcolo locale, senza richieste al modello. Le stime comprendono lettura ragionata, esempi, esercizi e riscontro; non garantiscono la preparazione all’esame.</p>
  </details>
 </section>;
}

export function useStudyClock(target:{sid:string,path:string,chapter:string,version:number,block:string}|null,enabled:boolean,onSaved:()=>Promise<void>){
 const key=target?.path??'',pauseKey='studio-study-time-paused:'+key,queueKey='studio-study-time-queue:'+key;
 const [paused,setPaused]=useState(()=>localStorage.getItem(pauseKey)==='true'),[state,setState]=useState('In pausa'),[error,setError]=useState('');
 const currentPath=useRef(key);currentPath.current=key;
 const owner=useRef(crypto.randomUUID()),lastInput=useRef(performance.now()),latestSaved=useRef(onSaved);latestSaved.current=onSaved;
 const flushRef=useRef<()=>Promise<void>>(async()=>{}),inFlight=useRef(false);
 useEffect(()=>{setPaused(localStorage.getItem(pauseKey)==='true');},[pauseKey]);
 const targetKey=JSON.stringify(target);
 useEffect(()=>{
  if(!target)return;const clock=new StudyClock(performance.now(),Date.now()),leaseKey='studio-study-time-owner:'+target.path;
  const readQueue=()=>{try{const value=JSON.parse(localStorage.getItem(queueKey)??'[]');return Array.isArray(value)?value:[];}catch{return [];}};
  const saveInterval=()=>{const queue=readQueue();let interval;while((interval=clock.take()))queue.push({...target,...interval,id:crypto.randomUUID()});localStorage.setItem(queueKey,JSON.stringify(queue));};
  const send=async()=>{
   if(inFlight.current)return;inFlight.current=true;
   try{let failure='';for(const item of readQueue()){try{
    const {path,...body}=item;await request('/sessions/'+item.sid+'/study-time/record',body);
    localStorage.setItem(queueKey,JSON.stringify(readQueue().filter((x:any)=>x.id!==item.id)));
   }catch(e:any){failure=e.message;}}setError(failure?'Tempo conservato nel browser; salvataggio da riprovare: '+failure:'');}catch(e:any){setError('Tempo conservato nel browser; salvataggio da riprovare: '+e.message);}finally{inFlight.current=false;}
  };
  const advance=()=>{
   const mono=performance.now();let owns=false;
   if(enabled&&!paused&&document.visibilityState==='visible'&&document.hasFocus()){
    try{const lease=JSON.parse(localStorage.getItem(leaseKey)??'null');if(!lease||lease.owner===owner.current||lease.until<Date.now()){localStorage.setItem(leaseKey,JSON.stringify({owner:owner.current,until:Date.now()+12000}));owns=true;}}catch{owns=true;}
   }
   if(!enabled||paused||document.visibilityState!=='visible'||!document.hasFocus()){try{const lease=JSON.parse(localStorage.getItem(leaseKey)??'null');if(lease?.owner===owner.current)localStorage.removeItem(leaseKey);}catch{}}
   const idle=mono-lastInput.current>180000,active=enabled&&!paused&&owns&&!idle;
   clock.advance(mono,Date.now(),active);setState(!enabled?'Rilevazione sospesa':paused?'Tempo in pausa':idle?'In pausa per inattività':owns?'Tempo in primo piano':'Tempo in pausa');
   if(!active)saveInterval();
  };
  const flush=async()=>{advance();saveInterval();await send();};flushRef.current=flush;
  const interact=()=>{lastInput.current=performance.now();advance();};
  const visibility=()=>{advance();saveInterval();void send();};
  ['pointerdown','keydown','scroll'].forEach(name=>document.addEventListener(name,interact,true));
  document.addEventListener('visibilitychange',visibility);window.addEventListener('blur',visibility);window.addEventListener('focus',interact);window.addEventListener('pagehide',visibility);
  advance();void send();let ticks=0;
  const timer=setInterval(()=>{advance();if(++ticks%6===0){saveInterval();void send();}},5000);
  return()=>{try{const lease=JSON.parse(localStorage.getItem(leaseKey)??'null');if(lease?.owner===owner.current)localStorage.removeItem(leaseKey);}catch{}clock.advance(performance.now(),Date.now(),false);saveInterval();void send();clearInterval(timer);['pointerdown','keydown','scroll'].forEach(name=>document.removeEventListener(name,interact,true));document.removeEventListener('visibilitychange',visibility);window.removeEventListener('blur',visibility);window.removeEventListener('focus',interact);window.removeEventListener('pagehide',visibility);};
 },[targetKey,enabled,paused,queueKey]);
 const toggle=async()=>{const next=!paused;await flushRef.current();localStorage.setItem(pauseKey,String(next));if(currentPath.current===key){lastInput.current=performance.now();setPaused(next);await latestSaved.current();}};
 return {paused,state,error,toggle,flush:()=>flushRef.current()};
}

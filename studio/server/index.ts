import express from 'express';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {existsSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
import {fsrs,createEmptyCard,Rating} from 'ts-fsrs';
import {Bridge} from './bridge';
import {Tutor} from './tutor';
import {CourseEngine} from './course-engine';
import {Embeddings} from './embeddings';
import {installationLoginOptions} from './login';
import {mathSpeech} from './math-speech';

const directory=path.dirname(fileURLToPath(import.meta.url));
const project=process.env.STUDIO_PROJECT??path.resolve(directory,'../..');
const configured=process.env.STUDIO_ROOT;
const python=process.env.STUDIO_PYTHON??(configured?path.join(configured,'.state/slides-runtime/bin/python'):'python3');
const bridge=new Bridge(python,project,configured);
const initial=await bridge.call('bootstrap');
const embeddings=new Embeddings(bridge,configured??path.resolve(initial.state_dir,'../..'),project);
const tutor=new Tutor(bridge,initial.state_dir,embeddings);
const courseEngine=new CourseEngine(bridge,tutor);
await courseEngine.recover();
const app=express();
app.disable('x-powered-by');
app.use((req,res,next)=>{
  const host=req.headers.host;
  if(!host||!/^127\.0\.0\.1:\d+$/.test(host)){res.status(403).json({error:'Host non ammesso.'});return;}
  const origin=req.headers.origin;
  if(origin&&origin!==`http://${host}`){res.status(403).json({error:'Origine non ammessa.'});return;}
  if(req.method!=='GET'&&!req.is('application/json')){res.status(415).json({error:'Richiesta JSON necessaria.'});return;}
  res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');next();
});
app.use(express.json({limit:'250kb'}));
const run=(handler:(req:any,res:any)=>Promise<any>)=>(req:any,res:any,next:any)=>{handler(req,res).catch(next);};
app.post('/api/math-speech',run(async(req,res)=>res.json(await mathSpeech(req.body.tex))));
app.get('/api/bootstrap',run(async(_req,res)=>res.json(await bridge.call('bootstrap'))));
app.post('/api/import',run(async(req,res)=>{const result=await bridge.call('import_course',{course:req.body.course});embeddings.index(req.body.course);res.json(result);}));
app.get('/api/courses/:course/inventory',run(async(req,res)=>res.json(await bridge.call('course_inventory',{course:req.params.course}))));
app.get('/api/courses/:course/paths',run(async(req,res)=>res.json(await bridge.call('course_paths',{course:req.params.course}))));
app.post('/api/paths',run(async(req,res)=>res.json(await bridge.call('course_create',req.body))));
app.get('/api/paths/:path',run(async(req,res)=>res.json(await bridge.call('course_path_view',{path:req.params.path,sid:req.query.sid||undefined}))));
app.post('/api/paths/:path/run',run(async(req,res)=>res.json(await courseEngine.start(req.params.path))));
app.post('/api/paths/:path/pause',run(async(req,res)=>res.json(await courseEngine.pause(req.params.path))));
app.post('/api/paths/:path/confirm',run(async(req,res)=>res.json(await bridge.call('course_confirm',{path:req.params.path,...req.body}))));
app.post('/api/paths/:path/recall',run(async(req,res)=>res.json(await courseEngine.recall(req.params.path,req.body.chapter))));
app.post('/api/sessions/:sid/recall/exit',run(async(req,res)=>res.json(await bridge.call('course_exit_recall',{sid:req.params.sid}))));
app.post('/api/paths/:path/open',run(async(req,res)=>res.json(await bridge.call('course_open',{...req.body,path:req.params.path}))));
app.post('/api/paths/:path/undo',run(async(req,res)=>res.json(await bridge.call('course_undo',{path:req.params.path,version:req.body.version}))));
app.post('/api/paths/:path/unlock',run(async(req,res)=>{await courseEngine.pause(req.params.path);res.json(await bridge.call('course_unlock',{path:req.params.path,document:req.body.document}));}));
app.post('/api/paths/:path/simulation',run(async(req,res)=>res.json(await bridge.call('course_simulation',{path:req.params.path,document:req.body.document}))));
app.post('/api/sessions/:sid/chapter',run(async(req,res)=>{const view=await bridge.call('course_select',{...req.body,sid:req.params.sid});if(view.curriculum)void courseEngine.start(view.curriculum.path);res.json(view);}));
app.post('/api/sessions/:sid/position',run(async(req,res)=>res.json(await bridge.call('course_position',{sid:req.params.sid,block:req.body.block}))));
app.post('/api/sessions/:sid/detour',run(async(req,res)=>res.json(await bridge.call('course_detour',{sid:req.params.sid,...req.body}))));
app.post('/api/sessions/:sid/diary',run(async(req,res)=>res.json(await bridge.call('course_note',{sid:req.params.sid,...req.body}))));
app.get('/api/courses/:course/diary/:note/evidence',run(async(req,res)=>res.json(await bridge.call('course_note_evidence',{course:req.params.course,note:req.params.note}))));
app.post('/api/courses/:course/diary/:note',run(async(req,res)=>res.json(await bridge.call('course_correct_note',{course:req.params.course,note:req.params.note,text:req.body.text}))));
app.get('/api/embeddings',(_req,res)=>res.json(Object.fromEntries(embeddings.jobs)));
app.get('/api/history',run(async(req,res)=>res.json(await bridge.call('list_sessions',{course:req.query.course||null,query:String(req.query.q??''),offset:Number(req.query.offset??0)}))));
app.post('/api/sessions',run(async(req,res)=>res.json(await bridge.call('open_session',req.body))));
app.post('/api/sessions/:sid/resume',run(async(req,res)=>res.json(await bridge.call('resume_session',{target:req.params.sid}))));
app.get('/api/sessions/:sid',run(async(req,res)=>res.json(await bridge.call('view',{sid:req.params.sid}))));
app.post('/api/sessions/:sid/beginner/advance',run(async(req,res)=>res.json(await bridge.call('advance_beginner',{sid:req.params.sid}))));
app.post('/api/sessions/:sid/beginner/lesson',run(async(req,res)=>res.json(await bridge.call('select_lesson',{sid:req.params.sid,lesson:req.body.lesson}))));
app.post('/api/sessions/:sid/beginner/unit',run(async(req,res)=>res.json(await bridge.call('select_beginner_unit',{sid:req.params.sid,unit:req.body.unit}))));
app.post('/api/sessions/:sid/beginner/recall',run(async(req,res)=>res.json(await bridge.call('beginner_recall',{sid:req.params.sid,lesson:req.body.lesson,unit:req.body.unit}))));
app.post('/api/sessions/:sid/next',run(async(req,res)=>res.json(await bridge.call('next',{sid:req.params.sid}))));
app.post('/api/sessions/:sid/recall',run(async(req,res)=>res.json(await bridge.call('recall',{sid:req.params.sid,concept:req.body.concept}))));
app.post('/api/sessions/:sid/select',run(async(req,res)=>res.json(await bridge.call('select_activity',{sid:req.params.sid,aid:req.body.aid,version:req.body.version}))));
app.post('/api/sessions/:sid/preferences',run(async(req,res)=>res.json(await bridge.call('preferences',{sid:req.params.sid,goal:req.body.goal,minutes:req.body.minutes}))));
app.get('/api/sessions/:sid/search',run(async(req,res)=>{const s=await bridge.call('context',{sid:req.params.sid});if(s.session.mode==='exam'||s.curriculum?.recall)throw Error('Ricerca sospesa durante la prova autonoma.');res.json(await embeddings.search(s.session.course,String(req.query.q??'')));}));
async function sourceFor(sid:string,id:string){const context=await bridge.call('context',{sid});if(context.curriculum?.recall)throw Error('Fonti nascoste durante il richiamo. Consegna o torna al capitolo.');const source=await bridge.call('source',{source_id:id,allow_reserved:context.session.mode==='exam',allow_solutions:context.session.mode!=='exam'});if(source.course!==context.session.course)throw Error('Fonte di un altro corso.');if(context.session.mode==='exam'&&!context.activity?.spec.sources.includes(id))throw Error('Fonte non disponibile durante la simulazione.');await bridge.call('course_expose',{course:source.course,document:source.document});return source;}
app.get('/api/sessions/:sid/sources/:id',run(async(req,res)=>{const source=await sourceFor(req.params.sid,req.params.id);res.json(source);}));
app.get('/api/sessions/:sid/page/:id',run(async(req,res)=>{const source=await sourceFor(req.params.sid,req.params.id);const image=await bridge.call('render_pdf',{source_id:source.id,allow_reserved:!!source.reserved,allow_solutions:!!source.solution});res.sendFile(image.path,{dotfiles:'allow'});}));
app.get('/api/sessions/:sid/media/:id',run(async(req,res)=>{
  const source=await sourceFor(req.params.sid,req.params.id);
  const root=process.env.STUDIO_ROOT??path.resolve(initial.state_dir,'../..');
  let file=path.resolve(root,source.path);
  if(!file.startsWith(path.resolve(root)+path.sep))throw Error('Percorso non ammesso.');
  if(source.kind==='video'||source.kind==='alignment')file=path.resolve(file,'../../video.mp4');
  if(!['pdf','video','alignment'].includes(source.kind))throw Error('Apri la cella nel pannello fonti.');
  if(!existsSync(file))throw Error('File non disponibile: collega il disco dati.');
  res.sendFile(file,{headers:{'Content-Security-Policy':"frame-ancestors 'self'"}});
}));
app.post('/api/sessions/:sid/events',run(async(req,res)=>{
  const {aid,version,event_id,kind,payload}=req.body;
  if(typeof event_id!=='string'||!event_id||typeof payload!=='object'||payload===null||Array.isArray(payload))throw Error('Evento non valido.');
  const result=await bridge.call('event',{sid:req.params.sid,aid,version,event_id,kind,payload});
  if(kind==='submit'&&result.attempt?.grade.status==='verified'){
    const s=await bridge.call('context',{sid:req.params.sid}),attempt=result.attempt;
    const old=await bridge.call('review',{course:s.session.course,concept:attempt.concept});
    const card=old?.card??createEmptyCard();
    for(const k of ['due','last_review'])if(card[k])card[k]=new Date(card[k]);
    const rating=attempt.grade.correct?(attempt.aids?Rating.Hard:Rating.Good):Rating.Again;
    const scheduled=fsrs().next(card,new Date(),rating);
    await bridge.call('review',{course:s.session.course,concept:attempt.concept,card:scheduled.card,attempt_id:attempt.id});
  }
  res.json(result);
}));
app.post('/api/sessions/:sid/assess',run(async(req,res)=>res.json(await tutor.assess(req.params.sid,req.body.attempt_id))));
app.post('/api/sessions/:sid/correct',run(async(req,res)=>res.json(await bridge.call('correct',{sid:req.params.sid,attempt_id:req.body.attempt_id,text:req.body.text}))));
app.get('/api/models',run(async(_req,res)=>res.json(await tutor.models())));
app.post('/api/model',run(async(req,res)=>{const {provider,id}=req.body;const catalog=await tutor.models();if(!catalog.models.some(m=>m.provider===provider&&m.id===id))throw Error('Modello non disponibile. Completa l’accesso al provider.');await bridge.call('setting',{name:'model',value:{provider,id}});res.json({saved:true});}));

// Auth uses Pi's provider-specific flow. Credentials never enter study history or logs.
const logins=new Map<string,{events:any[],prompt:any,resolve?:(value:string)=>void,status:string,error?:string,abort:AbortController}>();
app.post('/api/login',run(async(req,res)=>{
  await tutor.models();const {provider,type}=req.body;
  if(!['oauth','api_key'].includes(type))throw Error('Tipo accesso non valido.');
  const options=await installationLoginOptions(bridge);
  const id=randomUUID(),login={events:[] as any[],prompt:null as any,status:'pending',abort:new AbortController()} as any;
  logins.set(id,login);
  const timer=setTimeout(()=>{login.abort.abort();login.resolve?.('');logins.delete(id);},300000);
  void tutor.runtime!.login(provider,type,{signal:login.abort.signal,notify(event){login.events.push(event);},prompt(prompt){login.prompt=prompt;return new Promise<string>(resolve=>{login.resolve=(value:string)=>{login.prompt=null;resolve(value);};});}},options).then(()=>{login.status='done';}).catch(error=>{login.status='error';login.error=String(error.message).slice(0,300);}).finally(()=>clearTimeout(timer));
  res.json({id});
}));
app.get('/api/login/:id',run(async(req,res)=>{const login=logins.get(req.params.id);if(!login)throw Error('Accesso scaduto.');res.json({events:login.events,prompt:login.prompt,status:login.status,error:login.error});if(login.status!=='pending')logins.delete(req.params.id);}));
app.post('/api/login/:id',run(async(req,res)=>{const login=logins.get(req.params.id);if(!login?.resolve)throw Error('Nessuna risposta di accesso richiesta.');login.resolve(String(req.body.value??''));login.resolve=undefined;res.json({sent:true});}));
app.post('/api/sessions/:sid/chat',run(async(req,res)=>{
  const sid=req.params.sid,text=String(req.body.text??'').trim();if(!text||text.length>20000)throw Error('Scrivi un messaggio tra 1 e 20000 caratteri.');
  res.setHeader('Content-Type','text/event-stream');res.setHeader('Cache-Control','no-cache');res.flushHeaders();
  const send=(type:string,data:any)=>res.write(`data: ${JSON.stringify({type,...data})}\n\n`);
  const abort=()=>{void tutor.active.get(sid)?.abort();};res.on('close',abort);
  try{await tutor.chat(sid,text,delta=>send('delta',{text:delta}),req.body.automatic===true);send('done',{view:await bridge.call('view',{sid})});}
  catch(error:any){send('error',{error:error.message,view:await bridge.call('view',{sid})});}
  finally{res.off('close',abort);res.end();}
}));
app.post('/api/sessions/:sid/cancel',run(async(req,res)=>{await tutor.active.get(req.params.sid)?.abort();res.json({cancelled:true});}));
app.use(express.static(path.resolve(directory,'../dist')));
app.get('/{*splat}',(_req,res)=>res.sendFile(path.resolve(directory,'../dist/index.html')));
app.use((error:any,_req:any,res:any,_next:any)=>{if(!res.headersSent)res.status(400).json({error:error.message??'Operazione non riuscita.'});});
const server=app.listen(Number(process.env.STUDIO_PORT??4326),'127.0.0.1',()=>console.log(`Studio disponibile: http://127.0.0.1:${process.env.STUDIO_PORT??4326}`));
function close(){server.close();courseEngine.close();embeddings.close();bridge.close();process.exit(0);}
process.on('SIGINT',close);process.on('SIGTERM',close);

import React,{createContext,useContext,useEffect,useState} from 'react';

type Mode='whole'|'symbols'|'text';
const modes=new Set(['whole','symbols','text']);
const preference='studio-math-reading';
const Reading=createContext<{mode:Mode,setMode:(mode:Mode)=>void}>({mode:'whole',setMode:()=>{}});
function savedMode():Mode{try{const mode=localStorage.getItem(preference);return modes.has(mode??'')?mode as Mode:'whole';}catch{return 'whole';}}
export function MathReadingProvider({children}:{children:React.ReactNode}){
  const [mode,setMode]=useState<Mode>(savedMode);
  useEffect(()=>{document.documentElement.dataset.mathReading=mode;},[mode]);
  useEffect(()=>{const update=(event:StorageEvent)=>{if(event.key===preference)setMode(savedMode());};window.addEventListener('storage',update);return()=>window.removeEventListener('storage',update);},[]);
  return <Reading.Provider value={{mode,setMode:next=>{setMode(next);try{localStorage.setItem(preference,next);}catch{}}}}>{children}</Reading.Provider>;
}
export function MathReadingSettings(){
  const {mode,setMode}=useContext(Reading);
  return <details className="accessibility-settings"><summary>Accessibilità</summary><div className="accessibility-popover"><label>Modalità di lettura delle formule<select value={mode} onChange={e=>setMode(e.target.value as Mode)}><option value="whole">Formula intera</option><option value="symbols">Esplora i simboli</option><option value="text">Testo leggibile</option></select></label><p>“Formula intera” raggruppa i simboli per la lettura sotto il puntatore. “Testo leggibile” mostra la descrizione in parole. La preferenza viene ricordata.</p></div></details>;
}
export function formulaTex(node:any):string{
  if(node?.tagName==='annotation'&&node.properties?.encoding==='application/x-tex')return (node.children??[]).map((c:any)=>c.value??'').join('');
  for(const child of node?.children??[]){const tex=formulaTex(child);if(tex)return tex;}
  return '';
}
const descriptions=new Map<string,Promise<string>>();
function describe(tex:string){
  let pending=descriptions.get(tex);
  if(!pending){pending=fetch('/api/math-speech',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tex})}).then(async response=>{if(!response.ok)throw Error('Descrizione non disponibile');const result=await response.json();return String(result.speech);}).catch(error=>{descriptions.delete(tex);throw error;});if(descriptions.size>=512)descriptions.delete(descriptions.keys().next().value!);descriptions.set(tex,pending);}
  return pending;
}
export function AccessibleMath({tex,children}:{tex:string,children:React.ReactNode}){
  const {mode}=useContext(Reading);const [spoken,setSpoken]=useState<{tex:string,text:string}|null>(null);
  useEffect(()=>{let active=true;if(mode!=='symbols'&&tex)void describe(tex).then(text=>{if(active)setSpoken({tex,text});}).catch(()=>{});return()=>{active=false;};},[tex,mode]);
  if(!tex)return <>{children}</>;
  const speech=spoken?.tex===tex?spoken.text:tex;
  if(mode==='text')return <span className="math-readable" lang="it">{speech}</span>;
  return <span className="math-unit" role={mode==='whole'?'math':undefined} aria-label={mode==='whole'?speech:undefined} lang={mode==='whole'?'it':undefined}><span className="math-visual" aria-hidden={mode==='whole'?true:undefined}>{children}</span></span>;
}

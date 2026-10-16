import React,{createContext,useContext,useEffect,useLayoutEffect,useRef,useState} from 'react';

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
  return <details className="accessibility-settings"><summary>Accessibilità</summary><div className="accessibility-popover"><label>Modalità di lettura delle formule<select value={mode} onChange={e=>setMode(e.target.value as Mode)}><option value="whole">Formula intera</option><option value="symbols">Esplora i simboli</option><option value="text">Testo leggibile</option></select></label><p>“Formula intera” espone un testo unico sotto il puntatore, mantenendo la formula visiva. “Testo leggibile” mostra la descrizione in parole. La preferenza viene ricordata.</p></div></details>;
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
  const {mode}=useContext(Reading);const unit=useRef<HTMLSpanElement>(null),reading=useRef<HTMLSpanElement>(null);const [spoken,setSpoken]=useState<{tex:string,text:string}|null>(null);
  useEffect(()=>{let active=true;if(mode!=='symbols'&&tex)void describe(tex).then(text=>{if(active)setSpoken({tex,text});}).catch(()=>{});return()=>{active=false;};},[tex,mode]);
  const speech=spoken?.tex===tex?spoken.text:tex;
  useLayoutEffect(()=>{
    if(mode!=='whole'||!unit.current||!reading.current)return;
    const box=unit.current,text=reading.current;
    const fit=()=>{const width=text.offsetWidth,height=text.offsetHeight;if(width&&height)text.style.transform=`scale(${box.offsetWidth/width},${box.offsetHeight/height})`;};
    fit();const observer=new ResizeObserver(fit);observer.observe(box);observer.observe(text);
    return()=>observer.disconnect();
  },[mode,speech]);
  if(!tex)return <>{children}</>;
  if(mode==='text')return <span className="math-readable" lang="it">{speech}</span>;
  if(mode==='symbols')return <>{children}</>;
  // macOS pointer speech may skip ARIA math names. Give it an actual StaticText
  // node over the same rectangle, rather than hiding every readable descendant.
  return <span className="math-unit" ref={unit} lang="it"><span className="math-visual" aria-hidden="true">{children}</span><span className="math-spoken-hitbox" ref={reading}>{speech}</span></span>;
}

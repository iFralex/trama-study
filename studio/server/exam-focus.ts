export const EXAM_FOCUS_INSTRUCTIONS=`Se exam_policy.version=1, classifica ogni sezione dell'indice con focus:{role:"exam"|"foundation"|"support"|"uncertain",exam_refs:string[],reason:string} e depends_on:string[] (solo ID di sezioni precedenti). reason: massimo 240 caratteri; exam_refs: massimo 3 quesiti per sezione. exam = competenza direttamente richiesta da un quesito verificato pertinente; foundation = prerequisito realmente necessario per risolvere una competenza d'esame, anche in un capitolo successivo: motiva il collegamento e conserva spiegazioni complete, esempi e pratica guidata/autonoma. Entrambi richiedono exam_refs con ID di exam_policy.questions o di quesiti originali verificati recuperati con read_exam_profile. Se il pacchetto non basta a valutare una competenza o un suo prerequisito, usa read_exam_profile e leggi le fonti pertinenti, senza ristudiare tutto l’archivio. support = materiale del corso complementare senza collegamento necessario dimostrato; uncertain = riscontro insufficiente. Per support/uncertain spiega bene, con un esempio svolto se utile, ma non assegnare esercizi (solo kind=text); non nascondere consegne da svolgere nel testo. Sono ammessi esempi già risolti. L'assenza nei quesiti recuperati non dimostra esclusione dall'esame: non inventare riferimenti o probabilità. Dai maggior peso alle competenze exam e ai loro fondamenti; non classificare un intero capitolo in base a un solo argomento. Le attività possono usare solo nozioni già spiegate nelle sezioni depends_on e nei capitoli disponibili, senza attribuire allo studente padronanza non dimostrata. Per ogni attività autonoma exam crea una variante di uno dei quesiti di riferimento: stessa struttura, operazioni richieste e difficoltà; cambia dati, scenario o codice mantenendo ipotesi e soluzione coerenti. Per domande concettuali cambia esempi/affermazioni; non trasformare una risposta aperta in scelta multipla nella prova autonoma. spec.origin="adapted" e spec.exam_variant={question:ID,adaptation:descrizione delle variazioni entro 240 caratteri, senza soluzione}. Non basta sostituire numeri se servono nozioni successive. Gli esercizi foundation possono essere mirati e più semplici. I quiz guidati possono facilitare l'apprendimento, ma non sostituiscono il formato d'esame. Non ricopiare focus nei blocchi: lo conserva il servizio dall'indice. Le etichette rappresentano evidenze nel campione, non probabilità di uscita.`;

export function validateExamOutline(task:any,outline:any[]){
  if(task.exam_policy?.version!==1)return;
  const questions=new Set(task.exam_policy.questions.map((q:any)=>q.id)),previous=new Set<string>();
  for(const row of outline){
    const focus=row.focus,refs=focus?.exam_refs;
    if(!['exam','foundation','support','uncertain'].includes(focus?.role)||typeof focus?.reason!=='string'||!focus.reason.trim()||focus.reason.length>240||!Array.isArray(refs)||refs.length>3||refs.some((ref:any)=>typeof ref!=='string'||(!questions.has(ref)&&!/^[a-f0-9]{24}$/.test(ref))))throw Error('Indice di scrittura: priorità esame senza categoria, motivazione o quesiti verificati.');
    const training=['exam','foundation'].includes(focus.role);
    if(training&&!refs.length)throw Error('Indice di scrittura: Esame/Fondamento richiede un quesito verificato.');
    if(!training&&(refs.length||row.kind==='activity'))throw Error('Indice di scrittura: Complementare/Da verificare non prevede esercizi assegnati.');
    if((row.kind==='activity')!==['guided','independent'].includes(row.role))throw Error('Indice di scrittura: usa attività per le consegne guidate/autonome, testo per spiegazioni ed esempi svolti.');
    if(!Array.isArray(row.depends_on)||row.depends_on.some((id:any)=>typeof id!=='string'||!previous.has(id))||(row.kind==='activity'&&!row.depends_on.length))throw Error('Indice di scrittura: spiega i prerequisiti prima degli esercizi; dipendenze solo da sezioni precedenti.');
    previous.add(row.id);
  }
}

export function annotateExamBlocks(task:any,outline:any[],blocks:any[]){
  if(task.exam_policy?.version!==1)return blocks;
  return blocks.map(block=>{
    const row=outline.find(r=>r.id===block.id);
    if(!row)throw Error('Batch di scrittura: sezione assente nell’indice.');
    if(row.kind==='activity'&&row.focus.role==='exam'&&row.role==='independent'){
      const variant=block.spec?.exam_variant;
      if(block.spec?.origin!=='adapted'||!row.focus.exam_refs.includes(variant?.question)||typeof variant?.adaptation!=='string'||!variant.adaptation.trim()||variant.adaptation.length>240)throw Error('Batch di scrittura: l’esercizio autonomo richiede una variante dichiarata di un quesito verificato.');
      const question=task.exam_policy.questions.find((q:any)=>q.id===variant.question);
      const formats:Record<string,string[]>={open:['open'],numeric:['numeric','completion'],code:['open','completion'],mixed:['open'],choice:['choice'],unknown:['open']};
      // Questions retrieved with a tool are verified by the persistent checkpoint validator.
      if(question&&formats[question.format]&&!formats[question.format].includes(block.spec.kind))throw Error('Batch di scrittura: conserva il formato del quesito originale nella prova autonoma.');
    }
    return {...block,focus:structuredClone(row.focus),learning_role:row.role,depends_on:row.depends_on};
  });
}

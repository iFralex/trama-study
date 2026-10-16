import {Bridge} from './bridge';
import {Embeddings} from './embeddings';
const root=process.env.STUDIO_ROOT!;
const project=process.env.STUDIO_PROJECT!;
const bridge=new Bridge(process.env.STUDIO_PYTHON!,project,root);
const service=new Embeddings(bridge,root,project);
try{
 const course=process.argv[2]??(await bridge.call('bootstrap')).selected;
 await bridge.call('import_course',{course});
 await service.init();console.log('MODEL',service.model);service.index(course);
 const timer=setInterval(()=>console.log(JSON.stringify(service.jobs.get(course))),10000);
 while(service.jobs.get(course)?.running)await new Promise(r=>setTimeout(r,500));
 clearInterval(timer);if(service.jobs.get(course)?.error)throw Error(service.jobs.get(course)!.error);
 for(const query of ['Come si combinano molti numeri in un solo risultato usando un albero?','Quando più processori leggono la stessa cella, chi può scriverla?','How do adjacent GPU threads access consecutive memory locations?']){
  const results=await service.search(course,query,8);console.log(JSON.stringify({query,results:results.map((s:any)=>({id:s.id,title:s.title,page:s.page,score:s.semantic_score,method:s.retrieval}))}));
 }
 const fs=await import('node:fs/promises');
 const cases=[...JSON.parse(await fs.readFile(new URL('../tests/retrieval-cases.json',import.meta.url),'utf8')),...JSON.parse(await fs.readFile(new URL('../tests/semantic-cases.json',import.meta.url),'utf8'))];
 const results=[];
 for(const item of cases){const matches=await service.search(course,item.query,10);results.push({query:item.query,expected:item.documents,passed:matches.some((m:any)=>item.documents.includes(m.title)),results:matches.map((m:any)=>({id:m.id,title:m.title,page:m.page}))});}
 const report={date:new Date().toISOString(),model:service.model,course,passed:results.filter(r=>r.passed).length,total:results.length,results};
 await fs.writeFile(root+'/.state/studio/hybrid-verification.json',JSON.stringify(report,null,2));
 console.log('HYBRID',report.passed+'/'+report.total);if(report.passed!==report.total)process.exitCode=1;
 console.log('INDEX',JSON.stringify(await bridge.call('embedding_batch',{course,model:service.model})));
}finally{service.close();bridge.close();}

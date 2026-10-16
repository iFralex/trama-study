import path from 'node:path';
import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {Bridge} from './bridge';
const project=process.env.STUDIO_PROJECT??path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
if(!process.env.STUDIO_ROOT||!process.env.STUDIO_PYTHON)throw Error('Configura STUDIO_ROOT e STUDIO_PYTHON.');
const bridge=new Bridge(process.env.STUDIO_PYTHON,project,process.env.STUDIO_ROOT);
try{
  const boot=await bridge.call('bootstrap');
  const report=await bridge.call('import_course',{course:boot.selected});
  const cases=JSON.parse(await readFile(path.join(project,'studio/tests/retrieval-cases.json'),'utf8'));
  const results=[];
  for(const item of cases){const matches=await bridge.call('search',{course:boot.selected,query:item.query,limit:10});results.push({query:item.query,expected:item.documents,passed:matches.some((m:any)=>item.documents.includes(m.title)),results:matches.map((m:any)=>({id:m.id,title:m.title,page:m.page,quality:m.quality}))});}
  const output={date:new Date().toISOString(),course:boot.selected,import:report,passed:results.filter(r=>r.passed).length,total:results.length,results};
  await writeFile(path.join(boot.state_dir,'retrieval-verification.json'),JSON.stringify(output,null,2));
  console.log(`Ricerca: ${output.passed}/${output.total} casi annotati con documento atteso nei primi 10 risultati. ${report.passages} passaggi indicizzati.`);
  if(output.passed!==output.total)process.exitCode=1;
}finally{bridge.close();}

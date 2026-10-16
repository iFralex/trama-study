export type Model='EREW'|'CREW'|'CRCW';
export function simulate(values:number[],processors:number,algorithm:'reduction'|'scan',model:Model){
  if(!values.length||values.length>32||!values.every(Number.isFinite)||!Number.isInteger(processors)||processors<1||processors>32)throw Error('Dati non validi');
  const levels:{values:number[],operations:number,steps:number,concurrentReads:boolean}[]=[];
  let current=[...values],work=0,time=0;
  if(algorithm==='reduction'){
    while(current.length>1){
      const operations=Math.floor(current.length/2),next:number[]=[];
      for(let i=0;i<current.length;i+=2)next.push(i+1<current.length?current[i]+current[i+1]:current[i]);
      const steps=Math.ceil(operations/processors);work+=operations;time+=steps;
      levels.push({values:next,operations,steps,concurrentReads:false});current=next;
    }
  }else{
    for(let d=1;d<values.length;d*=2){
      const old=[...current],operations=values.length-d;
      current=old.map((v,i)=>i>=d?v+old[i-d]:v);
      const steps=Math.ceil(operations/processors);work+=operations;time+=steps;
      levels.push({values:[...current],operations,steps,concurrentReads:operations>d&&processors>1});
    }
  }
  // CREW is sufficient for the standard simultaneous-read scan; EREW requires another schedule.
  const supported=algorithm!=='scan'||model!=='EREW'||processors===1||values.length<=2;
  return {levels,result:current,work,time,depth:levels.length,supported,model,algorithm};
}

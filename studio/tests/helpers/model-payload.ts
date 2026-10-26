export function expandSources(packet:any){
 const texts=packet._source_texts??{};
 function expand(value:any):any{
  if(!value||typeof value!=='object')return value;
  if(Array.isArray(value))return value.map(expand);
  if(Object.keys(value).length===1&&typeof value.$ref==='string'&&value.$ref.startsWith('#/_source_texts/'))return texts[value.$ref.slice('#/_source_texts/'.length)];
  return Object.fromEntries(Object.entries(value).filter(([k])=>k!=='_source_texts').map(([k,v])=>[k,expand(v)]));
 }
 return expand(packet);
}

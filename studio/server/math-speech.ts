import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const sre=require('speech-rule-engine') as {setupEngine:(options:any)=>Promise<unknown>,engineReady:()=>Promise<unknown>,toSpeech:(xml:string)=>string};
const katex=require('katex') as {renderToString:(tex:string,options:any)=>string};
let ready:Promise<unknown>|undefined;
const cache=new Map<string,string>();

/** All rule files and computation stay local. Do not pass the KaTeX wrapper to SRE. */
export async function mathSpeech(tex:unknown){
  if(typeof tex!=='string'||!tex.trim()||tex.length>4000)throw Error('Formula non valida o troppo lunga.');
  const existing=cache.get(tex);if(existing)return {speech:existing,locale:'it'};
  ready??=sre.setupEngine({locale:'it',domain:'clearspeak',style:'ImpliedTimes_MoreImpliedTimes',markup:'none'}).then(()=>sre.engineReady());
  await ready;
  const rendered=katex.renderToString(tex,{output:'mathml',throwOnError:true,trust:false,maxExpand:1000,maxSize:20});
  // Speech convention for the course's cost function T(...), including compound
  // arguments. The invisible application operator only affects this MathML copy;
  // other parenthesized expressions, such as a(n+b), remain products.
  const xml=rendered.slice(rendered.indexOf('<math'),rendered.lastIndexOf('</math>')+7)
    .replace(/(<mi>T<\/mi>)(?=(?:<mrow>)*<mo\b[^>]*>\(<\/mo>)/g,'$1<mo>\u2061</mo>');
  const speech=sre.toSpeech(xml).trim();if(!speech)throw Error('Descrizione matematica non disponibile.');
  if(cache.size>=512)cache.delete(cache.keys().next().value!);cache.set(tex,speech);
  return {speech,locale:'it'};
}

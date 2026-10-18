/** Give each request, including a repair, its own bounded time window. */
export class PreparationTimeout extends Error {
  constructor(){super('Tempo limite della richiesta raggiunto. I checkpoint completati restano salvati; il compito incompleto puo essere ripreso.');this.name='PreparationTimeout';}
}
export async function promptWithDeadline(session:{prompt:(text:string)=>Promise<unknown>,abort:()=>Promise<void>},text:string,milliseconds:number){
  if(milliseconds<=0)throw new PreparationTimeout();
  let expired=false;
  let timer:ReturnType<typeof setTimeout>;
  const timeout=new Promise<never>((_resolve,reject)=>{timer=setTimeout(()=>{expired=true;reject(new PreparationTimeout());void session.abort().catch(()=>{});},milliseconds);});
  try{await Promise.race([session.prompt(text),timeout]);}
  catch(error){if(expired)throw new PreparationTimeout();throw error;}
  finally{clearTimeout(timer!);}
}

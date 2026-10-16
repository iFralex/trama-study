export function artifactDocument(html:string,token:string){
  const nonce=token.replace(/[^a-zA-Z0-9]/g,'');
  const bridge=`(()=>{const token=${JSON.stringify(token)};let state={},counter=0;const pending=new Map();
    window.study={emit:(kind,payload={})=>{if(!['change','try','submit','hint','explain','solution','reset'].includes(kind))return Promise.reject(Error('Azione non valida'));if(kind==='change'||kind==='try')state={...state,...payload};const id=String(++counter);const promise=new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});parent.postMessage({channel:'polimi-study',token,id,kind,payload},'*');});promise.catch(()=>{});return promise;},getState:()=>({...state})};
    document.addEventListener('input',event=>{const el=event.target,key=el.dataset?.key;if(key)window.study.emit('change',{[key]:el.type==='checkbox'?el.checked:el.value});});
    window.addEventListener('message',event=>{const data=event.data;if(event.source!==parent||data?.channel!=='polimi-ack'||data.token!==token)return;const request=pending.get(data.id);if(!request)return;pending.delete(data.id);data.ok?request.resolve(data.result):request.reject(Error('Non salvato sul disco. Riprova.'));});
    window.addEventListener('message',event=>{if(event.source!==parent||event.data?.channel!=='polimi-restore'||event.data.token!==token)return;state=event.data.state||{};for(const el of document.querySelectorAll('[data-key]')){const v=state[el.dataset.key];if(v!==undefined){if(el.type==='checkbox')el.checked=!!v;else el.value=v;}}window.dispatchEvent(new CustomEvent('study:restore',{detail:{...state}}));});
    window.addEventListener('error',event=>parent.postMessage({channel:'polimi-study',token,kind:'render_error',payload:{message:event.message}},'*'));
  })();`;
  const policy=`default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'none'; form-action 'none'; base-uri 'none'`;
  const header=`<style>:root{--study-bg:#fffefa;--study-fg:#283c36;--study-accent:#275e50;--study-muted:#718076;--study-line:#dedfd5}body{font:15px/1.6 system-ui;background:var(--study-bg);color:var(--study-fg);margin:0;padding:18px}button,input,select,textarea{font:inherit;border:1px solid var(--study-line);border-radius:8px;padding:8px}button{cursor:pointer;background:var(--study-accent);color:white}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid #ad8450;outline-offset:2px}</style><meta http-equiv="Content-Security-Policy" content="${policy}"><script nonce="${nonce}">${bridge}</script>`;
  // Every authored inline script shares a per-frame nonce; network and parent access remain blocked.
  const content=html.replace(/<script\b[^>]*>/gi,`<script nonce="${nonce}">`);
  return content.includes('<head>')?content.replace('<head>','<head>'+header):`<!doctype html><html><head>${header}</head><body>${content}</body></html>`;
}

export function validArtifactEvent(event:MessageEvent,frame:Window|null,token:string){
  const data=event.data;
  return event.source===frame&&data?.channel==='polimi-study'&&data.token===token&&
    ['change','try','submit','hint','explain','solution','reset','render_error'].includes(data.kind)&&
    data.payload!==null&&typeof data.payload==='object'&&!Array.isArray(data.payload)&&JSON.stringify(data.payload).length<=50000;
}

/** Accept conventional LaTeX delimiters without changing stored messages or code. */
export function normalizeMath(text:string):string{
  let out='',i=0;
  const escaped=(at:number)=>{let n=0;while(at>0&&text[--at]==='\\')n++;return n%2===1;};
  const closing=(token:string,from:number)=>{let at=text.indexOf(token,from);while(at>=0&&escaped(at))at=text.indexOf(token,at+token.length);return at;};
  while(i<text.length){
    if(i===0||text[i-1]==='\n'){
      const lineEnd=text.indexOf('\n',i),line=text.slice(i,lineEnd<0?undefined:lineEnd);
      const fence=/^ {0,3}(`{3,}|~{3,})/.exec(line);
      if(fence){
        const endPattern=new RegExp('^ {0,3}'+fence[1][0]+'{'+fence[1].length+',}[ \\t]*\\r?$','gm');
        endPattern.lastIndex=lineEnd<0?text.length:lineEnd+1;
        const end=endPattern.exec(text),stop=end?end.index+end[0].length:text.length;
        out+=text.slice(i,stop);i=stop;continue;
      }
      if(/^(?: {4}|\t)/.test(line)){const stop=lineEnd<0?text.length:lineEnd+1;out+=text.slice(i,stop);i=stop;continue;}
    }
    if(text[i]==='`'&&!escaped(i)){
      const ticks=/^`+/.exec(text.slice(i))![0];let end=text.indexOf(ticks,i+ticks.length);
      while(end>=0&&(text[end-1]==='`'||text[end+ticks.length]==='`'))end=text.indexOf(ticks,end+ticks.length);
      if(end>=0){out+=text.slice(i,end+ticks.length);i=end+ticks.length;continue;}
    }
    // Keep link destinations intact (labels can still contain inline math).
    if(text.startsWith('](',i)&&!escaped(i)){
      let end=i+2,depth=1;while(end<text.length&&depth){if(!escaped(end)){if(text[end]==='(')depth++;if(text[end]===')')depth--;}end++;}
      if(!depth){out+=text.slice(i,end);i=end;continue;}
    }
    if(text[i]==='$'&&!escaped(i)){
      const token=text.startsWith('$$',i)?'$$':'$',end=closing(token,i+token.length);
      if(end>=0){out+=text.slice(i,end+token.length);i=end+token.length;continue;}
    }
    if(!escaped(i)&&(text.startsWith('\\[',i)||text.startsWith('\\(',i))){
      const display=text[i+1]==='[',end=closing(display?'\\]':'\\)',i+2);
      if(end>=0){const body=text.slice(i+2,end).trim();if(body){out+=display?'\n$$\n'+body+'\n$$\n':'$'+body+'$';i=end+2;continue;}}
    }
    out+=text[i++];
  }
  return out;
}

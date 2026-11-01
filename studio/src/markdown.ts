/** Recognize disclosure wrappers without enabling arbitrary raw HTML. */
export function studyDetails(this:any){
  const parse=(text:string)=>this.parse(text);
  return (tree:any)=>{
    function visit(parent:any){
      if(!parent.children)return;
      for(const child of parent.children)visit(child);
      const output:any[]=[],stack:any[]=[];
      const append=(node:any)=>(stack.at(-1)?.children??output).push(node);
      for(const node of parent.children){
        if(node.type!=='html'){append(node);continue;}
        const pattern=/\s*(<details(?:\s+open)?\s*>|<\/details\s*>|<summary\s*>[\s\S]*?<\/summary\s*>)\s*/gy;
        const tokens:string[]=[];let match:RegExpExecArray|null,offset=0;
        while((match=pattern.exec(node.value))){tokens.push(match[1]);offset=pattern.lastIndex;}
        if(offset!==node.value.length||!tokens.length){append(node);continue;}
        for(const token of tokens){
          if(/^<details\b/.test(token)){
            const details={type:'studyDetails',data:{hName:'details',hProperties:/\sopen\b/.test(token)?{open:true}:{}},children:[]};
            append(details);stack.push(details);
          }else if(/^<\/details/.test(token)){
            if(!stack.length)return; // Leave malformed markup as literal text.
            stack.pop();
          }else{
            if(!stack.length)return;
            const title=token.replace(/^<summary\s*>|<\/summary\s*>$/g,'');
            const children=parse(title).children.flatMap((child:any)=>child.type==='paragraph'?child.children:[child]);
            append({type:'studySummary',data:{hName:'summary'},children});
          }
        }
      }
      if(!stack.length)parent.children=output;
    }
    visit(tree);
  };
}

/** Restore authored indentation after Markdown-to-HTML trims soft breaks.
 * Code blocks keep their own whitespace and are never rewritten.
 */
export function preserveParagraphIndentation(){
  return (tree:any,file:any)=>{
    const source=String(file.value);
    function visit(node:any){
      if(node.tagName==='p'&&node.position){
        const raw=source.slice(node.position.start.offset,node.position.end.offset);
        const indents=[...raw.matchAll(/\r?\n([ \t]*)/g)].map(match=>match[1]);
        let index=0;
        function restore(child:any){
          if(child.type==='text')child.value=child.value.replace(/\n[ \t]*/g,()=> '\n'+(indents[index++]??''));
          // Inline code and math have their own rendering rules.
          if(child.tagName==='code'||child.properties?.className?.includes('katex'))return;
          for(const item of child.children??[])restore(item);
        }
        restore(node);return;
      }
      for(const child of node.children??[])visit(child);
    }
    visit(tree);
  };
}

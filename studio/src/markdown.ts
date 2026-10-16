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

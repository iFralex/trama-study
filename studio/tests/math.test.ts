import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import Markdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import {normalizeMath} from '../src/math';
const render=(text:string)=>renderToStaticMarkup(createElement(Markdown,{remarkPlugins:[remarkMath],rehypePlugins:[rehypeKatex],children:normalizeMath(text)}));

test('the reported lecture formula and inline LaTeX render as KaTeX',()=>{
 const block=render(String.raw`Vogliamo calcolare:
\[
(2+3)\times(4+5)
\]`);
 assert.match(block,/class="katex-display"/);assert.match(block,/<math /);assert.match(block,/>×</);
 const inline=render(String.raw`Il tempo è \(T_p = n/p\).`);assert.match(inline,/class="katex"/);assert.doesNotMatch(inline,/katex-display/);
 assert.match(render('$$\nx^2\n$$'),/katex-display/);
});

test('math normalization preserves code, existing math and citation destinations',()=>{
 const code='Inline: `\[x\]`\n\n````latex\n\[x\]\n```\n````';
 const html=render(code);assert.doesNotMatch(html,/class="katex/);assert.match(html,/<code/);
 const examples=['`\(x\)`', '    '+String.raw`\[x\]`, String.raw`$\text{\[x\]}$`,String.raw`[Fonte](https://example.org/a\(b\))`,String.raw`\\[x\\]`];
 for(const example of examples)assert.equal(normalizeMath(example),example);
 assert.equal(normalizeMath(String.raw`\[x+1`),String.raw`\[x+1`);
});

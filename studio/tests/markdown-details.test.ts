import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import Markdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import {studyDetails} from '../src/markdown';

const render=(text:string)=>renderToStaticMarkup(createElement(Markdown,{remarkPlugins:[remarkMath,studyDetails],rehypePlugins:[rehypeKatex],children:text}));

test('support consultations render as disclosures with Markdown and formulas inside',()=>{
  const html=render('### Consultazioni di supporto\n\n<details>\n<summary>Notazione **asintotica**</summary>\n\n**Conoscenza generale.** Il costo è $n^2$.\n\n- Un limite\n- Una condizione\n\n</details>\n\nDopo la consultazione.');
  assert.match(html,/<details><summary>Notazione <strong>asintotica<\/strong><\/summary>/);
  assert.match(html,/<p><strong>Conoscenza generale\.<\/strong>/);
  assert.match(html,/class="katex"/);assert.match(html,/<ul>/);
  assert.match(html,/<\/details>\n<p>Dopo la consultazione\.<\/p>/);
  assert.doesNotMatch(html,/&lt;details/);
});

test('nested disclosures preserve their default open state',()=>{
  const html=render('<details open>\n<summary>Esterno</summary>\n\n<details>\n<summary>Interno</summary>\n\nTesto.\n\n</details>\n\n</details>');
  assert.match(html,/<details open=""><summary>Esterno<\/summary>/);
  assert.equal((html.match(/<details/g)??[]).length,2);
  assert.equal((html.match(/<\/details>/g)??[]).length,2);
});

test('other HTML, attributes, code and incomplete wrappers remain literal',()=>{
  const html=render('<details onclick="alert(1)">\n<summary>Titolo</summary>\n\n<script>alert(1)</script>\n\n</details>');
  assert.doesNotMatch(html,/<details|<script|<summary/);
  assert.match(render('```html\n<details><summary>Esempio</summary></details>\n```'),/&lt;details/);
  const incomplete=render('<details>\n<summary>Titolo</summary>\n\nContenuto ancora in arrivo.');
  assert.doesNotMatch(incomplete,/<details/);assert.match(incomplete,/Contenuto ancora in arrivo/);
});

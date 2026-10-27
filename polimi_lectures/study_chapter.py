"""Unpublished, validated chapter checkpoints and lossless recovery of complete JSON blocks."""
import copy
import json
import math
import re


def recover_chapter_blocks(text):
    """Decode a complete array prefix; never close or repair a truncated JSON value."""
    decoder = json.JSONDecoder();text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    if not text.startswith('{'):
        return []
    position = 1
    while position < len(text):
        while position < len(text) and (text[position].isspace() or text[position] == ','):
            position += 1
        try:
            key, position = decoder.raw_decode(text, position)
            while text[position].isspace():position += 1
            if text[position] != ':':return []
            position += 1
            while text[position].isspace():position += 1
            if key != 'blocks':
                _, position = decoder.raw_decode(text, position);continue
            if text[position] != '[':return []
            position += 1;blocks = []
            while position < len(text):
                while position < len(text) and (text[position].isspace() or text[position] == ','):position += 1
                try:block, position = decoder.raw_decode(text, position)
                except ValueError:break
                if not isinstance(block, dict):break
                blocks.append(block)
            return blocks
        except (ValueError, IndexError):return []
    return []


class ChapterPreparation:
    @staticmethod
    def _repair_targets(task):
        blocks=task['draft']['blocks'];ids={b['id'] for b in blocks}
        issues=[i for review in task.get('reviews',{}).values() for i in review.get('issues',[])]
        affected={i.get('block') for i in issues}
        return [b['id'] for b in blocks if not issues or not affected<=ids or b['id'] in affected]

    def _repair_block_validate(self,path,task,block):
        original=next((b for b in task['draft']['blocks'] if b['id']==block.get('id')),None)
        if not original or block.get('kind')!=original['kind']:raise ValueError('Identità del blocco corretto non valida.')
        if block==original:return
        self._prep_refs(path,task,block.get('sources',block.get('spec',{}).get('sources',[])))
        self._chapter_blocks_normalized(task,[block])
        content=dict(task['draft'],blocks=[block if b['id']==block['id'] else b for b in task['draft']['blocks']])
        self._validate_chapter_content(path,task['chapter']['id'],content)
        self._deterministic_checks(copy.deepcopy(content))

    def _repair_recovery(self,path,task,metrics):
        """Retain validated replacements; return incomplete ones only as untrusted repair input."""
        if task['kind']!='repair_chapter':return None
        targets=self._repair_targets(task);saved=metrics.get('repair_checkpoint',{});done={};pending={}
        candidates=[]
        if saved.get('version')==1 and saved.get('targets')==targets:
            pending.update((b['id'],b) for b in saved.get('pending_blocks',[]) if b.get('id') in targets)
        for row in self.db.execute('SELECT output FROM prep_rejections WHERE path=? AND task=? ORDER BY rowid DESC LIMIT 1',(path,task['task_id'])):
            try:
                content=json.loads(row['output']);blocks=content['blocks']
                if [b['id'] for b in blocks]!=[b['id'] for b in task['draft']['blocks']]:continue
                if any(b!=old for b,old in zip(blocks,task['draft']['blocks']) if old['id'] not in targets):continue
                self._validate_chapter_content(path,task['chapter']['id'],content)
                self._deterministic_checks(copy.deepcopy(content))
                candidates.extend(b for b in blocks if b['id'] in targets)
            except (ValueError,TypeError,KeyError):continue
        if saved.get('version')==1 and saved.get('targets')==targets:candidates.extend(saved.get('blocks',[]))
        for block in candidates:
            if block.get('id') not in targets:continue
            try:self._repair_block_validate(path,task,block)
            except (ValueError,KeyError,TypeError):pending[block['id']]=block;continue
            done[block['id']]=block;pending.pop(block['id'],None)
        if not done and not pending:return None
        return {'version':1,'targets':targets,'blocks':[done[i] for i in targets if i in done],'pending_blocks':[pending[i] for i in targets if i in pending and i not in done]}

    def _chapter_blocks_normalized(self, task, blocks):
        result = copy.deepcopy(blocks)
        for block in result:
            owner = block.get('spec', {}) if block.get('kind') == 'activity' else block
            refs = owner.get('sources', [])
            urls = [r for r in refs if isinstance(r, str) and r.startswith('https://')]
            external = list(dict.fromkeys(owner.get('external_sources', []) + urls))
            if any(not self.db.execute('SELECT 1 FROM prep_external WHERE task=? AND url=?', (task['task_id'], url)).fetchone() for url in external):
                raise ValueError('Fonte web del capitolo non letta nel compito: usa read_web_page prima di citarla.')
            if urls:
                owner['sources'] = [r for r in refs if r not in urls]
            if external:
                owner['external_sources'] = external
            check = owner.get('verification', {});data = check.get('input', {})
            if check.get('model') in ('amdahl', 'gustafson') and isinstance(data, dict):
                if 'p' in data:
                    if 'processors' in data and data['processors'] != data['p']:
                        raise ValueError('Verifica dello scaling: p e processors sono discordanti.')
                    data.setdefault('processors', data['p'])
                alias = 'parallel_fraction' if check['model'] == 'amdahl' else 'serial_fraction'
                if alias in data:
                    if 'fraction' in data and data['fraction'] != data[alias]:
                        raise ValueError('Verifica dello scaling: frazioni dichiarate discordanti.')
                    data.setdefault('fraction', data[alias])
                if 'serial_fraction' in data and 'parallel_fraction' in data:
                    if not math.isclose(data['serial_fraction'] + data['parallel_fraction'], 1, abs_tol=1e-9):
                        raise ValueError('Verifica dello scaling: le due frazioni devono sommare a uno.')
        return result

    def _chapter_prefix_validate(self, path, task, blocks):
        blocks = self._chapter_blocks_normalized(task, blocks)
        if blocks:
            self._validate_chapter_content(path, task['chapter']['id'], {'blocks': blocks})
            for block in blocks:
                self._prep_refs(path, task, block.get('sources', block.get('spec', {}).get('sources', [])))
            self._deterministic_checks({'blocks': blocks})
        return blocks

    def _chapter_recovery(self, path, task):
        if task['kind'] != 'chapter':return None
        row = self.db.execute('SELECT metrics FROM prep_tasks WHERE id=? AND path=?', (task['task_id'], path)).fetchone()
        saved = json.loads(row[0] or '{}').get('chapter_checkpoint', {}) if row else {}
        blocks = saved.get('blocks', []) if saved.get('version') == 1 else []
        outline = saved.get('outline', []) if saved.get('version') == 1 else []
        # A legacy response is one whole chapter; newer responses are only the requested batch.
        for row in self.db.execute('SELECT data FROM prep_model_calls WHERE task=? AND path=? ORDER BY rowid DESC LIMIT 4', (task['task_id'], path)):
            call = json.loads(row['data']);candidate = recover_chapter_blocks(call.get('output', ''))
            if call.get('protocol') == 'chapter-batches-1':
                if call.get('error') and outline and candidate and [b.get('id') for b in candidate] == [b['id'] for b in outline[len(blocks):len(blocks) + len(candidate)]]:
                    try:blocks = self._chapter_prefix_validate(path, task, blocks + candidate)
                    except (ValueError, KeyError, TypeError):pass
            elif len(candidate) > len(blocks) and (not blocks or candidate[:len(blocks)] == blocks):
                blocks = candidate
        if not blocks and not outline:return None
        try:
            normalized = self._chapter_prefix_validate(path, task, blocks)
            return {'version': 1, 'outline': outline, 'blocks': normalized, 'error': ''}
        except (ValueError, KeyError, TypeError) as error:
            return {'version': 1, 'outline': outline, 'blocks': blocks, 'error': str(error)}

    def preparation_chapter_checkpoint(self, path, task, checkpoint):
        row = self.db.execute('SELECT input,state,metrics FROM prep_tasks WHERE path=? AND id=?', (path, task)).fetchone()
        if not row or row['state'] not in ('running', 'waiting', 'correcting'):
            raise ValueError('Compito non attivo.')
        original = json.loads(row['input'])
        if original['kind'] != 'chapter' or checkpoint.get('version') != 1:
            raise ValueError('Checkpoint di scrittura non valido.')
        outline = checkpoint.get('outline', []);blocks = checkpoint.get('blocks', [])
        limit = original['chapter_limits']['max_blocks']
        if not isinstance(outline, list) or not 3 <= len(outline) <= limit or any(not isinstance(r, dict) or not r.get('id') or r.get('kind') not in ('text', 'activity') for r in outline):
            raise ValueError('Indice dei blocchi del capitolo non valido.')
        ids = [r['id'] for r in outline]
        if len(set(ids)) != len(ids) or not isinstance(blocks, list) or [b.get('id') for b in blocks] != ids[:len(blocks)]:
            raise ValueError('I blocchi salvati devono seguire esattamente l’indice, senza duplicati.')
        if len(blocks) > len(outline) or any(b.get('kind') != r['kind'] for b, r in zip(blocks, outline)):
            raise ValueError('Tipo o numero di blocchi incoerente con l’indice.')
        blocks = self._chapter_prefix_validate(path, original, blocks)
        metrics = json.loads(row['metrics'] or '{}');previous = metrics.get('chapter_checkpoint', {})
        if previous.get('version') == 1:
            old_blocks = previous.get('blocks', [])
            if blocks[:len(old_blocks)] != old_blocks or (previous.get('outline') and outline != previous['outline']):
                raise ValueError('Conserva i blocchi già salvati e l’indice della scrittura; aggiungi soltanto le parti mancanti.')
        saved = {'version': 1, 'outline': outline, 'blocks': blocks}
        metrics['chapter_checkpoint'] = saved
        with self.db:
            self.db.execute('UPDATE prep_tasks SET metrics=? WHERE path=? AND id=?', (json.dumps(metrics, ensure_ascii=False), path, task))
        return saved

"""Small, evidence-backed exam packets and per-section teaching policy."""
import copy
import json
import re
from pathlib import Path


FOCUS_ROLES = ('exam', 'foundation', 'support', 'uncertain')


def validate_focus_rows(policy, rows):
    questions = {q['id']: q for q in policy.get('questions', [])}
    previous = set()
    for row in rows:
        focus = row.get('focus', {})
        if not isinstance(focus, dict):
            raise ValueError('Priorità esame: classificazione non valida.')
        role = focus.get('role')
        refs = focus.get('exam_refs')
        if role not in FOCUS_ROLES or not isinstance(focus.get('reason'), str) or not 1 <= len(focus['reason'].strip()) <= 240:
            raise ValueError('Priorità esame: ogni sezione richiede categoria e motivazione breve.')
        if not isinstance(refs, list) or len(refs)>3 or any(not isinstance(ref, str) or ref not in questions for ref in refs):
            raise ValueError('Priorità esame: riferimento a un quesito non verificato o non disponibile.')
        if role in ('exam', 'foundation') and not refs:
            raise ValueError('Priorità esame: collega Esame/Fondamento a un quesito verificato; altrimenti usa Da verificare.')
        if role in ('support', 'uncertain') and (refs or row.get('kind') == 'activity'):
            raise ValueError('Priorità esame: Complementare/Da verificare richiede spiegazioni senza esercizi assegnati.')
        dependencies = row.get('depends_on', [])
        if not isinstance(dependencies, list) or any(not isinstance(ref, str) or ref not in previous for ref in dependencies):
            raise ValueError('Priorità esame: una sezione può dipendere soltanto da sezioni precedenti.')
        if row.get('kind') == 'activity' and not dependencies:
            raise ValueError('Priorità esame: spiega i prerequisiti prima di assegnare un esercizio.')
        if row.get('role') not in ('explain', 'worked', 'guided', 'independent', 'recap'):
            raise ValueError('Priorità esame: ruolo didattico della sezione non valido.')
        if (row.get('kind')=='activity') != (row.get('role') in ('guided','independent')):
            raise ValueError('Priorità esame: le consegne guidate/autonome devono essere attività, le spiegazioni blocchi di testo.')
        previous.add(row['id'])
    training = any(r['focus']['role'] in ('exam', 'foundation') for r in rows)
    if not any(r.get('role') == 'explain' and r['kind'] == 'text' for r in rows) or (training and (not any(r.get('role') == 'worked' and r['kind'] == 'text' for r in rows) or not any(r.get('role') == 'independent' and r['kind'] == 'activity' for r in rows))):
        raise ValueError('Priorità esame: servono spiegazione e, per Esame/Fondamento, esempio svolto e prova autonoma.')


class ExamFocusStudy:
    def _exam_focus_questions(self, path):
        """Read verified questions, never solutions, reserved pages or protected excerpts."""
        from .study_course import is_exam
        rows = self.db.execute('SELECT q.id,q.data,d.path FROM course_questions q JOIN documents d ON d.id=q.document WHERE q.path=? ORDER BY q.id', (path,))
        result = []
        cached_sources = {}
        for row in rows:
            q = json.loads(row['data'])
            if not is_exam(row['path']) or q.get('origin') != 'exam' or not q.get('authenticity_verified') or not q.get('in_scope', True):
                continue
            try:
                sources = []
                for ref in q.get('sources', []):
                    if ref not in cached_sources:
                        cached_sources[ref] = self.source(ref, allow_solutions=False)
                    sources.append(cached_sources[ref])
            except ValueError:
                continue
            if not sources or any(s['kind'] != 'pdf' for s in sources):
                continue
            # Protection may have changed since the question was extracted.
            text = ' '.join(q.get('text', '').split())
            if not text or text not in ' '.join(' '.join(s['text'].split()) for s in sources):
                continue
            label = Path(row['path']).name + ' · p. ' + ', '.join(str(s['page']) for s in sources)
            result.append({**{key: q[key] for key in ('text', 'format', 'skills', 'operations', 'points', 'options', 'subparts', 'sources') if key in q}, 'id': row['id'], 'label': label, 'family': q.get('family', row['id'])})
        return result

    def _exam_focus_policy(self, path, chapter, plan):
        """Rank locally; send a few complete templates, not the entire exam archive."""
        questions = self._exam_focus_questions(path)
        chapters = plan['data']['chapters']
        descendants = {chapter['id']}
        for _ in chapters:
            added = {c['id'] for c in chapters if set(c.get('prerequisites', [])) & descendants}
            if added <= descendants:
                break
            descendants |= added
        def words(value):
            return set(re.findall(r'[\w]{4,}', value.casefold()))
        def rank(c):
            terms = words(' '.join([c['title'], c.get('objective', ''), *c.get('exam_skills', [])]))
            refs = set(c.get('sources', []))
            return sorted(((len(words(' '.join(q.get('skills', [])) + ' ' + q['text']) & terms) + 8 * bool(refs & set(q['sources'])), q) for q in questions), key=lambda item: (-item[0], item[1]['id']))
        selected = []
        used = set()
        used_families = set()
        for c in [chapter] + [c for c in chapters if c['id'] in descendants and c['id'] != chapter['id']]:
            count = 0
            for score, q in rank(c):
                if score <= 0 or q['id'] in used or q['family'] in used_families:
                    continue
                candidate = {**{key: value for key, value in q.items() if key != 'family'}, 'target': c['id']}
                if len(json.dumps(selected + [candidate], ensure_ascii=False)) > 16000:
                    continue
                selected.append(candidate);used.add(q['id']);used_families.add(q['family']);count += 1
                if len(selected) >= 8 or count >= (6 if c['id'] == chapter['id'] else 2):
                    break
            if len(selected) >= 8:
                break
        prior = []
        for c in chapters:
            if c['id'] == chapter['id']:
                break
            if self._chapter(path, c['id']):
                prior.append({'id': c['id'], 'title': c['title']})
        return {'version': 1, 'questions': selected, 'available_chapters': prior,
                'limitations': 'Campione recuperato da quesiti verificati pertinenti; assenza nel pacchetto non dimostra assenza dagli esami o esclusione dal programma. Disponibile non significa padronanza dimostrata.'}

    def _exam_focus_blocks(self, task, outline, blocks):
        if task.get('exam_policy', {}).get('version') != 1:
            return blocks
        policy = task['exam_policy']
        known = {q['id'] for q in policy['questions']}
        requested = {ref for row in outline if isinstance(row.get('focus'), dict) and isinstance(row['focus'].get('exam_refs'), list) for ref in row['focus']['exam_refs'] if isinstance(ref, str)}
        if requested - known:
            # The author may retrieve additional verified questions on demand.
            row = self.db.execute('SELECT path FROM prep_tasks WHERE id=?', (task['task_id'],)).fetchone()
            extra = [q for q in self._exam_focus_questions(row['path']) if q['id'] in requested - known] if row else []
            policy = dict(policy, questions=policy['questions'] + extra)
        validate_focus_rows(policy, outline)
        rows = {r['id']: r for r in outline}
        questions = {q['id']: q for q in policy['questions']}
        result = copy.deepcopy(blocks)
        for block in result:
            row = rows.get(block.get('id'))
            if not row:
                raise ValueError('Priorità esame: blocco non presente nell’indice.')
            focus = row['focus']
            block['focus'] = {key: copy.deepcopy(focus[key]) for key in ('role', 'exam_refs', 'reason')}
            block['focus']['references'] = [{'question': ref, 'label': questions[ref]['label'], 'sources': questions[ref]['sources']} for ref in focus['exam_refs']]
            block['learning_role'] = row['role']
            block['depends_on'] = row.get('depends_on', [])
            if block['kind'] == 'activity' and focus['role'] == 'exam' and row['role'] == 'independent':
                spec = block.get('spec', {});variant = spec.get('exam_variant', {})
                if not isinstance(variant,dict):
                    raise ValueError('Priorità esame: la variante richiede un quesito e una breve descrizione delle modifiche.')
                if spec.get('origin') != 'adapted' or variant.get('question') not in focus['exam_refs'] or not isinstance(variant.get('adaptation'), str) or not 1 <= len(variant['adaptation'].strip()) <= 240:
                    raise ValueError('Priorità esame: l’esercizio autonomo deve essere una variante dichiarata di un quesito verificato.')
                expected = {'open': ('open',), 'numeric': ('numeric', 'completion'), 'code': ('open', 'completion'), 'mixed': ('open',), 'choice': ('choice',), 'unknown': ('open',)}.get(questions[variant['question']].get('format'))
                if expected and spec.get('kind') not in expected:
                    raise ValueError('Priorità esame: la prova autonoma deve conservare il formato del quesito originale.')
        return result

    def _exam_focus_review_policy(self, path, content):
        if content.get('exam_focus_version') != 1:
            return None
        refs = {ref for b in content['blocks'] for ref in b.get('focus', {}).get('exam_refs', [])}
        questions = [q for q in self._exam_focus_questions(path) if q['id'] in refs]
        if {q['id'] for q in questions} != refs:
            raise ValueError('Priorità esame: un quesito di riferimento non è più disponibile per questo percorso.')
        return {'version': 1, 'questions': questions}

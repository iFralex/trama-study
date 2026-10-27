"""Local, course-independent study effort estimates. Uses stored data; never calls a model or opens original documents."""
import copy
import hashlib
import html
import json
import math
import re
import statistics
import time
from datetime import datetime, timezone

VERSION = 'study-time-1'
PRACTICE = {'choice': 2, 'numeric': 5, 'completion': 4, 'open': 10, 'explain': 7, 'html': 8, 'code': 12, 'essay': 15}


def fingerprint(block):
    value = copy.deepcopy(block)
    if value.get('kind') == 'activity':
        value = {'id': value['id'], 'kind': 'activity', 'spec': {k: v for k, v in value['spec'].items() if k not in ('curriculum', 'concept', 'grading_origin')}}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def visible_metrics(text):
    text = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', str(text), flags=re.S | re.I)
    text = html.unescape(re.sub(r'</?(?:p|div|span|strong|em|a|ul|ol|li|h[1-6]|br|input|button|label|select|option)\b[^>]*>', ' ', text, flags=re.I))
    code = re.findall(r'```[^\n]*\n(.*?)```|~~~[^\n]*\n(.*?)~~~', text, re.S)
    lines = sum(sum(bool(line.strip()) for line in (a or b).splitlines()) for a, b in code)
    text = re.sub(r'```.*?```|~~~.*?~~~', ' ', text, flags=re.S)
    displays = re.findall(r'\$\$(.*?)\$\$|\\\[(.*?)\\\]', text, re.S)
    text = re.sub(r'\$\$.*?\$\$|\\\[.*?\\\]', ' ', text, flags=re.S)
    inline = re.findall(r'(?<!\\)\$(?!\$)(.*?)(?<!\\)\$', text)
    text = re.sub(r'(?<!\\)\$(?!\$).*?(?<!\\)\$', ' ', text)
    images = len(re.findall(r'!\[[^\]]*\]\([^)]*\)', text))
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', text)
    text = re.sub(r'\[[^\]]*\]\((?:source:|https?://)[^)]*\)', ' ', text)
    text = re.sub(r'https?://\S+', ' ', text)
    # CJK scripts need a character-based fallback rather than one "word" per paragraph.
    cjk = re.findall(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', text)
    other = re.sub(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', ' ', text)
    words = len(re.findall(r'\w+', other)) + len(cjk) / 2
    return {'words': round(words), 'code_lines': lines, 'inline_formulas': len(inline), 'display_formulas': len(displays), 'images': images}


def block_effort(block):
    spec = block.get('spec', {})
    kind = spec.get('kind', 'open') if block.get('kind') == 'activity' else 'reading'
    text = block.get('text', '') if kind == 'reading' else '\n'.join(str(x) for x in [spec.get('prompt', ''), *(spec.get('options') or []), spec.get('assumptions', ''), spec.get('fallback', '') if kind == 'html' else ''])
    metrics = visible_metrics(text)
    reading = max(.3, metrics['words'] / 150 + metrics['code_lines'] * .20 + metrics['inline_formulas'] * .15 + metrics['display_formulas'] * .7 + metrics['images'])
    parts = len(re.findall(r'(?m)^\s*(?:\d+|[a-hA-H])[.)]\s+', spec.get('prompt', '')))
    practice = 0 if kind == 'reading' else PRACTICE.get(kind, 10) * (1 + .15 * max(0, min(8, parts - 1)))
    review = 0 if kind == 'reading' else practice * .25 + .5
    return {'id': block['id'], 'fingerprint': fingerprint(block), 'type': kind, 'reading': reading, 'practice': practice, 'review': review, 'base': reading + practice + review, 'metrics': metrics}


def planned_units(chapter):
    skills = set(str(s).strip().casefold() for s in chapter.get('exam_skills', []) if str(s).strip())
    words = visible_metrics(chapter.get('objective', '') + '\n' + chapter.get('assessment', ''))['words']
    return max(3, min(24, max(len(skills), math.ceil(words / 80))))


def band(minutes, low=.7, high=1.5):
    if minutes <= 0:
        return {'low': 0, 'high': 0}
    return {'low': max(1, math.floor(minutes * low)), 'high': max(1, math.ceil(minutes * high))}


def add_bands(values):
    return {k: sum(v[k] for v in values) for k in ('low', 'high')}


class StudyTimeStudy:
    def setup_study_time(self):
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS study_time_marks(path TEXT,chapter TEXT,block TEXT,fingerprint TEXT,status TEXT,updated TEXT,PRIMARY KEY(path,chapter,block,fingerprint));
        CREATE TABLE IF NOT EXISTS study_time_segments(id TEXT PRIMARY KEY,course TEXT,path TEXT,session TEXT,chapter TEXT,version INTEGER,block TEXT,fingerprint TEXT,started REAL,ended REAL,seconds REAL,payload TEXT);
        CREATE INDEX IF NOT EXISTS study_time_intervals ON study_time_segments(course,started,ended);
        CREATE TABLE IF NOT EXISTS study_time_options(path TEXT PRIMARY KEY,daily_minutes INTEGER,tracking INTEGER DEFAULT 1,updated TEXT);
        ''')
        self._study_time_cache = {}

    def _time_target(self, sid, chapter, version, block):
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError('Versione del capitolo non valida.')
        session = self.session(sid);link = self._path_for_session(sid)
        if not link or session['mode'] != 'learn':
            raise ValueError('Tempo di studio disponibile solo nel percorso di apprendimento.')
        if self.db.execute('SELECT 1 FROM course_recall_runs WHERE session=? AND finished=0', (sid,)).fetchone():
            raise ValueError('Il tempo del capitolo è sospeso durante il richiamo.')
        detail = self._chapter(link['path'], chapter, version)
        if not detail or not self.db.execute('SELECT 1 FROM course_chapter_exposure WHERE path=? AND chapter=?', (link['path'], chapter)).fetchone():
            raise ValueError('Apri il capitolo prima di registrare lo studio.')
        target = next((b for b in detail['content']['blocks'] if b['id'] == block), None)
        if not target:
            raise ValueError('Blocco non disponibile in questa versione del capitolo.')
        return session, link, target

    def study_time_mark(self, sid, chapter, version, block, status):
        if status not in ('studied', 'review', 'todo'):
            raise ValueError('Stato di studio non valido.')
        _, link, target = self._time_target(sid, chapter, version, block)
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO study_time_marks VALUES(?,?,?,?,?,?)', (link['path'], chapter, block, fingerprint(target), status, datetime.now(timezone.utc).isoformat()))
        return self.course_study_time(link['path'], sid, chapter, version)

    def study_time_settings(self, path, daily_minutes, tracking=True, sid=None, chapter=None, version=None):
        self._path(path)
        if isinstance(daily_minutes, bool) or not isinstance(daily_minutes, int) or not 5 <= daily_minutes <= 600 or not isinstance(tracking, bool):
            raise ValueError('Scegli da 5 a 600 minuti al giorno e una preferenza di rilevazione valida.')
        if sid and (not self._path_for_session(sid) or self._path_for_session(sid)['path'] != path):
            raise ValueError('Sessione di un altro percorso.')
        if chapter is not None or version is not None:
            if not sid or not chapter or not isinstance(version, int) or not self._chapter(path, chapter, version):
                raise ValueError('Versione del capitolo non disponibile.')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO study_time_options VALUES(?,?,?,?)', (path, daily_minutes, int(tracking), datetime.now(timezone.utc).isoformat()))
        return self.course_study_time(path, sid, chapter, version)

    def study_time_record(self, sid, chapter, version, block, id, started, ended, seconds):
        session, link, target = self._time_target(sid, chapter, version, block)
        if not isinstance(id, str) or not 1 <= len(id) <= 100 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in (started, ended, seconds)):
            raise ValueError('Intervallo di studio non valido.')
        duration = (ended - started) / 1000
        if not 0 < seconds <= 60 or not 0 < duration <= 60 or seconds > duration + 2 or started < 0 or ended > time.time() * 1000 + 60000:
            raise ValueError('Intervallo di studio fuori dai limiti.')
        raw = json.dumps([sid, chapter, version, block, started, ended, seconds])
        previous = self.db.execute('SELECT payload FROM study_time_segments WHERE id=?', (id,)).fetchone()
        if previous:
            if previous[0] != raw:
                raise ValueError('Identificativo di intervallo già usato per altri dati.')
            return {'saved': True, 'duplicate': True}
        option = self.db.execute('SELECT tracking FROM study_time_options WHERE path=?', (link['path'],)).fetchone()
        if option and not option[0]:
            return {'saved': False, 'disabled': True}
        # Union the existing intervals, so retries and overlapping tabs never double count time.
        cursor = started;available = 0
        for row in self.db.execute('SELECT started,ended FROM study_time_segments WHERE course=? AND ended>? AND started<? ORDER BY started', (session['course'], started, ended)):
            a, b = max(started, row[0]), min(ended, row[1])
            if a > cursor:
                available += a - cursor
            cursor = max(cursor, b)
        available += max(0, ended - cursor)
        accepted = min(seconds, duration) * available / (ended - started)
        with self.db:
            self.db.execute('INSERT INTO study_time_segments VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (id, session['course'], link['path'], sid, chapter, version, block, fingerprint(target), started, ended, accepted, raw))
        return {'saved': True, 'seconds': accepted}

    def _time_calibration(self, course):
        samples = {}
        rows = self.db.execute('''SELECT t.path,t.chapter,t.block,t.fingerprint,sum(t.seconds) seconds
          FROM study_time_segments t JOIN study_time_marks m ON m.path=t.path AND m.chapter=t.chapter AND m.block=t.block AND m.fingerprint=t.fingerprint
          WHERE t.course=? AND m.status='studied' GROUP BY t.path,t.chapter,t.block,t.fingerprint''', (course,))
        for row in rows:
            detail = self._chapter(row['path'], row['chapter'])
            block = next((b for b in (detail or {}).get('content', {}).get('blocks', []) if b['id'] == row['block'] and fingerprint(b) == row['fingerprint']), None)
            if not block:
                continue
            effort = block_effort(block);ratio = row['seconds'] / 60 / effort['base']
            if row['seconds'] >= 20 and .25 <= ratio <= 4:
                samples.setdefault(effort['type'], []).append(ratio)
        result = {}
        for kind, values in samples.items():
            n = len(values);median = statistics.median(values)
            result[kind] = {'samples': n, 'factor': max(.5, min(2.5, (n * median + 6) / (n + 6))) if n >= 3 else 1}
        return result

    def course_study_time(self, path, sid=None, chapter=None, version=None):
        p = self._path(path);course = p['course']
        link = self._path_for_session(sid) if sid else None
        if sid and (not link or link['path'] != path):
            raise ValueError('Sessione di un altro percorso.')
        if chapter is not None or version is not None:
            if not link or not chapter or not isinstance(version, int) or not self._chapter(path, chapter, version):
                raise ValueError('Versione del capitolo non disponibile.')
            link = dict(link, chapter=chapter, version=version)
        versions = list(self.db.execute('SELECT chapter,max(version) version FROM course_chapters WHERE path=? GROUP BY chapter ORDER BY chapter', (path,)))
        plan_version = self.db.execute('SELECT max(version) FROM course_plans WHERE path=?', (path,)).fetchone()[0]
        mark_version = tuple(self.db.execute('SELECT count(*),max(updated) FROM study_time_marks WHERE path IN (SELECT id FROM course_paths WHERE course=?)', (course,)).fetchone())
        segment_version = self.db.execute('SELECT max(rowid) FROM study_time_segments WHERE course=?', (course,)).fetchone()[0]
        options = self.db.execute('SELECT * FROM study_time_options WHERE path=?', (path,)).fetchone()
        attempt_version = tuple(tuple(r) for r in self.db.execute("SELECT id,json_extract(grade,'$.correct') FROM attempts WHERE concept LIKE ? ORDER BY rowid", (path+':%',)))
        recall_version = self.db.execute('SELECT count(*) FROM course_recalls WHERE path=? AND card IS NOT NULL', (path,)).fetchone()[0]
        question_version = tuple(tuple(r) for r in self.db.execute("SELECT json_extract(data,'$.format'),json_extract(data,'$.in_scope'),json_extract(data,'$.authenticity_verified'),count(*) FROM course_questions WHERE path=? GROUP BY 1,2,3 ORDER BY 1,2,3", (path,)))
        key = (path, p['objective'].get('minutes'), tuple(p['objective'].get('reserved', [])), question_version, attempt_version, recall_version, plan_version, tuple(tuple(v) for v in versions), (link['chapter'], link['version']) if link else None, mark_version, segment_version, tuple(options) if options else None)
        cache = getattr(self, '_study_time_cache', {})
        if key in cache:
            return copy.deepcopy(cache[key])
        plan = self._plan(path);calibration = self._time_calibration(course)
        daily = options['daily_minutes'] if options else p['objective'].get('minutes') or 30
        rows = [];current_blocks = []
        profile = self.course_exam_profile(path) if plan else {'formats': {}}
        # Learn content density conservatively, within this course, with six prior chapters.
        reading_densities = [];activity_densities = []
        for candidate in (plan or {}).get('data', {}).get('chapters', []):
            published = self._chapter(path, candidate['id'])
            if not published:
                continue
            efforts = [block_effort(b) for b in published['content']['blocks']]
            units = planned_units(candidate)
            reading_densities.append(sum(b['reading'] for b in efforts) / units)
            activity_densities.append(sum(b['type'] != 'reading' for b in efforts) / units)
        n = min(10, len(reading_densities))
        reading_density = (6 * 2.5 + n * max(1, min(8, statistics.median(reading_densities)))) / (6 + n) if n else 2.5
        activity_density = (6 * .5 + n * max(.25, min(2, statistics.median(activity_densities)))) / (6 + n) if n else .5
        formats = profile.get('formats', {});format_count = sum(formats.values())
        average_practice = sum(PRACTICE.get(kind, 10) * calibration.get(kind, {}).get('factor', 1) * count for kind, count in formats.items()) / format_count if format_count else 10
        for chapter in (plan or {}).get('data', {}).get('chapters', []):
            pinned = link['version'] if link and link['chapter'] == chapter['id'] else None
            detail = self._chapter(path, chapter['id'], pinned)
            if not detail:
                units = planned_units(chapter)
                exercises = max(1, math.ceil(units * activity_density))
                reading = units * reading_density * calibration.get('reading', {}).get('factor', 1)
                practice = exercises * average_practice
                feedback = practice * .25 + exercises * .5
                predicted = reading + practice + feedback
                total = band(predicted, .5, 1.8)
                rows.append({'id': chapter['id'], 'basis': 'plan', 'total': total, 'remaining': dict(total), 'breakdown': {'reading': band(reading, .5, 1.8), 'practice': band(practice, .5, 1.8), 'review': band(feedback, .5, 1.8)}, 'planned_units': units, 'planned_activities': exercises, 'studied_blocks': 0, 'review_blocks': 0, 'blocks': 0, 'version': None})
                continue
            marks = {r['fingerprint']: r['status'] for r in self.db.execute('SELECT fingerprint,status FROM study_time_marks WHERE path=? AND chapter=?', (path, chapter['id']))}
            attempted = {}
            for row in self.db.execute('''SELECT a.created,a.grade,v.spec,i.block FROM attempts a JOIN activities v ON v.id=a.activity AND v.version=a.version
              JOIN course_chapter_activities i ON i.activity=a.activity AND i.activity_version=a.version
              JOIN course_path_sessions s ON s.session=i.session WHERE s.path=? AND i.chapter=? ORDER BY a.created''', (path, chapter['id'])):
                spec = json.loads(row['spec']);candidate = {'id': row['block'], 'kind': 'activity', 'spec': spec}
                attempted[fingerprint(candidate)] = json.loads(row['grade'])
            blocks = [];totals = {'reading': 0, 'practice': 0, 'review': 0};remaining = 0
            for block in detail['content']['blocks']:
                effort = block_effort(block);factor = calibration.get(effort['type'], {}).get('factor', 1)
                for part in totals:
                    totals[part] += effort[part] * factor
                value = effort['base'] * factor;status = marks.get(effort['fingerprint'], 'todo');left = value
                grade = attempted.get(effort['fingerprint'])
                if status == 'studied':
                    left = 0
                elif status == 'review':
                    left = value * .6
                elif grade is not None:
                    left = (effort['review'] + (effort['practice'] * .6 if grade.get('correct') is False else 0)) * factor
                remaining += left
                blocks.append({'id': block['id'], 'type': effort['type'], 'status': status, 'submitted': grade is not None, 'total': band(value), 'remaining': band(left)})
            total = band(sum(totals.values()))
            rows.append({'id': chapter['id'], 'basis': 'content', 'version': detail['version'], 'total': total, 'remaining': band(remaining), 'breakdown': {k: band(v) for k, v in totals.items()}, 'blocks': len(blocks), 'studied_blocks': sum(b['status'] == 'studied' for b in blocks), 'review_blocks': sum(b['status'] == 'review' for b in blocks)})
            if link and link['chapter'] == chapter['id']:
                current_blocks = blocks
        total = add_bands([c['total'] for c in rows]);remaining = add_bands([c['remaining'] for c in rows])
        recalls = self.db.execute('SELECT count(*) FROM course_recalls WHERE path=? AND card IS NOT NULL', (path,)).fetchone()[0]
        seconds = self.db.execute('SELECT COALESCE(sum(seconds),0) FROM study_time_segments WHERE path=?', (path,)).fetchone()[0]
        result = {'version': VERSION, 'available': bool(rows), 'total': total, 'remaining': remaining, 'chapters': rows, 'current_blocks': current_blocks, 'forecast_basis_chapters': len(reading_densities), 'forecast_chapters': sum(c['basis'] == 'plan' for c in rows), 'daily_minutes': daily, 'default_daily_minutes': not options and not p['objective'].get('minutes'), 'study_days': {k: math.ceil(remaining[k] / daily) for k in ('low', 'high')}, 'scheduled_recalls': {'count': recalls, 'time': band(recalls * 8)}, 'recorded_minutes': round(seconds / 60, 1), 'tracking': bool(options['tracking']) if options else True, 'calibration': calibration, 'observed_samples': sum(c['samples'] for c in calibration.values()), 'calibrated_samples': sum(c['samples'] for c in calibration.values() if c['samples'] >= 3), 'scope': 'Primo studio ragionato, esercizi e revisione del riscontro; ripassi già programmati separati.'}
        if len(cache) > 24:
            cache.clear()
        cache[key] = copy.deepcopy(result);self._study_time_cache = cache
        return result
